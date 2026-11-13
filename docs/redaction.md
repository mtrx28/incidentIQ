# Redaction

PII and secrets are removed from text before a language model sees it. The code is in `incidentiq/redaction.py`; the evaluation is `incidentiq/eval/redaction_eval.py`, with raw results in [`results/redaction/`](../results/redaction/results.md).

## Design

**Layered detectors.** `redact(text)` runs a list of detectors in a fixed priority order. Each yields spans (start, end, type, detector name). A later detector never touches text that an earlier one already claimed, so overlapping matches resolve in favour of the earlier rule.

1. credentials inside URLs (`scheme://user:PASSWORD@host`)
2. AWS-style access key IDs (`AKIA` or `ASIA` plus 16 characters)
3. bearer tokens
4. key-value secrets (`api_key=`, `secret=`, `token=`, `password=`, `passwd=`, `pwd=`, `access_key=`)
5. email addresses
6. card numbers (13 to 19 digits, accepted only if the Luhn checksum passes)
7. phone numbers (need a leading `+`)
8. Aadhaar-style 12-digit IDs (accepted only if the Verhoeff checksum passes)
9. IPv4 addresses
10. names after a `user=` field
11. a high-entropy token detector for long random-looking strings nothing else recognised (it skips hex IDs shorter than 32 characters and snake_case or kebab-case identifiers)

**Typed, stable placeholders.** A match is replaced by a placeholder such as `[EMAIL_1]`, `[PHONE_1]`, `[NAME_1]`, `[CARD_1]`, `[ID_1]` (Aadhaar-style), `[IP_1]` or `[SECRET_1]`. A `Redactor` object keeps the value-to-placeholder map for one incident, so the same value always gets the same placeholder. The agent can then still see that two log lines mention the same user. Values are normalised first (emails lower-cased, digits and `+` kept for cards, IDs and phones). Findings record the position and detector, never the value.

**One shared Redactor.** The agent's `act` node and the LLM client use the same `Redactor` object, so placeholder numbering never collides between tool output and prompts.

**Defence in depth.**

1. The `act` node redacts every tool result (summary, evidence excerpts, arguments) before it is stored in the graph state.
2. The LLM client redacts every message before it is sent and every reply before it is returned, whatever mode is in use (replay, live or mock). The exact redacted prompts are kept in `client.sent` for tests and audits.
3. Each benchmark run checks the prompts actually sent for any injected value from `data/pii_manifest.json`. That count is reported in each run's `results.md` and is 0 in all five runs.
4. `tests/test_redaction.py` fetches every injected line through the real `log_search` tool, redacts it, and fails if any injected value survives. A companion test shows the check can fail (with a no-op redactor it finds more than 500 leaks).

## What was measured

Both tables below are generated from `results/redaction/results.json`.

<!-- BEGIN GENERATED:redaction-doc (python scripts/make_readme_tables.py --write) -->
Injected set: 601/601 caught (100.0%). Independent hand-written hard set: 25/42 (59.5%). Clean lines altered: 119/20656 (0.6%).

| Type | Injected set (caught / total) | Hard set (caught / total) |
|---|---|---|
| aadhaar | 59/59 (100.0%) | 2/3 (66.7%) |
| card | 60/60 (100.0%) | 2/3 (66.7%) |
| email | 60/60 (100.0%) | 3/4 (75.0%) |
| gov_id | - | 0/1 (0.0%) |
| ip | 54/54 (100.0%) | 4/5 (80.0%) |
| name | 58/58 (100.0%) | 1/5 (20.0%) |
| phone | 61/61 (100.0%) | 2/6 (33.3%) |
| secret_apikey | 60/60 (100.0%) | 3/3 (100.0%) |
| secret_aws | 61/61 (100.0%) | 2/2 (100.0%) |
| secret_password | 66/66 (100.0%) | 2/6 (33.3%) |
| secret_token | 62/62 (100.0%) | 4/4 (100.0%) |

| Look-alike type (clean) | Tokens | Altered | Rate | Detector that fired |
|---|---|---|---|---|
| hex_id | 4780 | 1 | 0.0% | aadhaar_verhoeff (1) |
| order_ref | 968 | 118 | 12.2% | aadhaar_verhoeff (118) |
| sha | 689 | 0 | 0.0% | - |
| version | 746 | 0 | 0.0% | - |
<!-- END GENERATED:redaction-doc -->

A value counts as caught only if the full original string is gone from the redacted line.

- **Injected set, 601 of 601.** The injected items come from the same generator the detectors were written against (`scripts/datagen/pii.py`), so this number is optimistic.
- **Hand-written hard set, 25 of 42 (59.5%).** `incidentiq/eval/redaction_hard_cases.py` holds 42 lines in formats the generator does not use, written separately; the redactor was not tuned to them. This is the more realistic estimate for real logs, and the one to quote for coverage.
- **False positives: 119 of 20,656 clean lines altered (0.6%).** The look-alike table above breaks this down. The most confused look-alike is the 12-digit order reference, which is mistaken for an Aadhaar-style ID: 118 of 968 order references were altered, and the Aadhaar checksum detector accounts for all 119 altered clean lines (118 order references and 1 hex ID). SHAs and version strings were never altered.
- **Gold evidence lines altered: 6 of 116.** Six lines that are gold evidence for an incident were changed by redaction (for example a JDBC password or bearer token in a connection-failure line). The line is still retrievable and the text around the placeholder is intact.

## The Verhoeff note

Real Aadhaar numbers end in a Verhoeff check digit, and the generator gives its fake Aadhaar numbers a valid one, so the checksum test is a fair match for the data. A random 12-digit number passes the checksum about 1 time in 10 (measured here: 118 of 968 order references, 12.2%). An ablation turns the checksum off (`results/redaction/results.json`, `ablation_no_aadhaar_checksum`): Aadhaar recall stays 100.0%, but 100.0% of 12-digit order references are altered (968 of 968) and 976 of 20,656 clean lines change (4.7%), against 0.6% with the checksum. The cost of the checksum is that an ID with a wrong or missing check digit (a typo, a different ID scheme) would not be caught.

## The hard-set misses, and why

17 of the 42 hard-set lines were not fully redacted. Reasons read from the patterns in `redaction.py`:

| Missed value (fake) | Why it is missed |
|---|---|
| `98765 43210`, `09876543210`, `(415) 555-0132` | The phone pattern needs a leading `+`. |
| `+44 (0)20 7946 0958` | The `(0)` in brackets does not fit the digit-group pattern. |
| `Priya Sharma`, `Rahul Iyer`, `Ananya Gupta`, `Meera Nair` | Names are only caught after `user=`. There is no named-entity recognition. 1 of 5 hard-set names was caught. |
| `priya.sharma%40gmail.com` | The email pattern needs a literal `@`; here it is URL-encoded as `%40`. |
| `4111.1111.1111.1111` and `2345.6789.0124` | Card and Aadhaar patterns accept spaces and hyphens as separators, not dots. |
| `ABCDE1234F` (a PAN-style ID) | No detector exists for it. |
| `2001:db8:85a3::8a2e:370:7334` | Only IPv4 is matched. |
| `"password": "Zebra#7781q"` | The key-value pattern needs `=` or `:` right after the key name; here a closing quote comes first. |
| `login with pwd Maple#4821x` | No `=` or `:` after `pwd`. |
| `mysql -u root -pWinter2024!x` | No key name; the password is attached to a `-p` flag. |
| `redis://:p4ssW0rdX9@redis-1` | The URL-credential pattern needs a non-empty username before the colon. |

By type, the hard set caught all API keys, AWS-style keys and bearer or token secrets it contained (3, 2 and 4), and was weakest on names (1 of 5), phones (2 of 6) and passwords (2 of 6).

Consequences: regex redaction is a first layer, not a guarantee. Free-text names and unusual phone formats can reach the model. A named-entity model and broader patterns would be the next step; they are not built.

## The GitHub secret-scanning note

The generator writes fake secrets, and some real-looking formats make GitHub's secret scanning block a push. So it uses non-vendor prefixes for API keys (`iq_sk_`, `iq_pk_`, `key_` rather than, for example, Stripe's `sk_live_`), and AWS-style key IDs in which at least one character is `0`, `1`, `8` or `9`, which real AWS key IDs never contain (they use `A-Z` and `2-7` only). The redactor does not rely on that: its AWS pattern accepts any `[A-Z0-9]` after `AKIA` or `ASIA`. The hard-set cases alter vendor-specific key formats for the same reason.
