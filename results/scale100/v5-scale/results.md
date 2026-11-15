# v5-scale

v4 plus rarity-ranked log_search with a default window around the alert and a count/template header (and a prompt addendum describing them). Built for the scale100 condition; scope fixed in docs/benchmark-scale100.md.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v5-scale --llm replay --condition scale100`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 88.0% (22/25; 95% CI 70.0% to 95.8%) | 86.7% (13/15; 95% CI 62.1% to 96.3%) | 87.5% (35/40; 95% CI 73.9% to 94.5%) |
| Strict accuracy (category + cites gold cause evidence) | 84.0% (21/25) | 86.7% (13/15) | 85.0% (34/40) |
| Citation validity (cited IDs that exist) | 99.4% | 100.0% | 99.6% |
| Citation support, lexical check | 94.1% | 100.0% | 96.3% |
| Citation support, gold check | 56.3% | 63.4% | 59.0% |
| Gold evidence recall | 61.8% | 60.5% | 61.3% |
| Gold runbook section cited | 52.0% | 66.7% | 57.5% |
| Cause evidence retrieved at all | 88.0% | 86.7% | 87.5% |
| Tool calls per incident | 4.64 | 4.93 | 4.75 |
| LLM calls per incident | 6.52 | 7.00 | 6.70 |
| Reporter retries per incident | 0.32 | 0.53 | 0.40 |
| Prompt / completion tokens per incident | 22721 / 1753 | 24376 / 1929 | 23341 / 1819 |
| LLM latency per incident (recorded) | 12.8 s | 16.5 s | 14.2 s |
| Unverified diagnoses / failed runs / tool errors | 4 / 0 / 0 | 1 / 0 / 0 | 5 / 0 / 0 |

## Accuracy by category (test)

| Category | Correct | n |
|---|---|---|
| bad_deployment | 2 | 2 |
| cache_stampede_outage | 2 | 3 |
| db_connection_pool_exhaustion | 2 | 2 |
| disk_full | 2 | 3 |
| downstream_timeout | 2 | 2 |
| expired_tls_cert | 3 | 3 |
| memory_leak_oom | 2 | 2 |
| misconfiguration | 2 | 3 |
| slow_query_missing_index | 2 | 2 |
| traffic_spike_rate_limit | 3 | 3 |

## Accuracy by case type (test)

| Case | Correct | n |
|---|---|---|
| logs_only | 1 | 1 |
| metrics_only | 0 | 2 |
| overlapping | 1 | 1 |
| runbook_needed | 0 | 1 |
| standard | 20 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (5 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-005 | test | metrics_only | cache_stampede_outage | downstream_timeout | 6 | never retrieved the cause evidence | (not yet analysed) |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 6 | never retrieved the cause evidence | (not yet analysed) |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | misconfiguration | 5 | never retrieved the cause evidence; no runbook retrieved; unverified after retries | (not yet analysed) |
| INC-035 | test | runbook_needed | misconfiguration | bad_deployment | 6 | - | (not yet analysed) |
| INC-036 | dev | standard | expired_tls_cert | bad_deployment | 5 | never retrieved the cause evidence | (not yet analysed) |
