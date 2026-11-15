# IncidentIQ

An incident-diagnosis agent for on-call engineers, built on LangGraph, Pydantic and pgvector, with an evaluation harness that scores it against labeled synthetic incidents.

> **Demo recording: not yet recorded.** (Placeholder. A terminal recording of `make demo` will go here.)

## The problem

When an alert fires, an on-call engineer spends the first minutes collecting evidence: which metrics moved, which log lines matter, whether a runbook covers it. IncidentIQ automates that collection. Given an alert such as "checkout-service: HTTP error rate above 5% for 5 minutes", it queries metrics, searches logs and retrieves runbook sections, then proposes a root cause where every claim cites the evidence behind it. It only recommends. It never changes anything.

It runs on synthetic data bundled in the repo (40 labeled incidents, 18 runbooks), so anyone can run it. This repo is also an evaluation study: the same model is run through five system versions (a single-call baseline and four agent versions) and scored the same way. The results section reports what was measured, including the parts that do not flatter the agent.

## Architecture

```
                 +----------------------------------------------+
   alert ------> |   LangGraph graph (step cap: 8 tool calls)   |
                 +----------------------------------------------+

   planner --(more steps)--> act --> observe --> planner ...      plan-act-observe loop
   planner --(done, or cap reached)--> reporter --> verifier
   verifier --(problems found, up to 2 retries)--> reporter
   verifier --(passed, or retries used up)--> END

   planner   picks the next tool calls, or says "done"
   act       runs the tools, redacts the results, gives every item an evidence ID
   observe   reads the new results and updates the hypotheses
   reporter  writes the Pydantic `Diagnosis`; every claim cites evidence IDs
   verifier  checks that the citations exist, that actions cite runbooks, and that the
             cited text supports the claim (lexical overlap, optional LLM check)

   tools (read-only):  metrics_query      log_search        runbook_retrieve
                       (CSV time series)  (keyword search)  (pgvector cosine similarity)
                              |                 |                  |
              +---------- Redaction layer (PII and secrets) -------+
                                        |
                    LLM client: replay (default) | live | mock
                    every prompt and every reply is redacted again here

   v0 baseline (outside the graph): one LLM call with the alert and the last 100 log lines.
```

**Walkthrough.** The planner reads the alert and the evidence so far and proposes tool calls. The act node runs them. Every string a tool returns passes through the redactor before it is stored or shown to a model, and each item gets a deterministic evidence ID (`L-0271` for a log line, `M-048` for a metric series, `R-02-6` for a runbook section). The observe node asks the model to update its hypotheses from the new results. When the planner says it is done, or 8 tool calls have been used, the reporter writes the diagnosis as a Pydantic model. The verifier then checks it. If a check fails, the problems go back to the reporter, at most twice. After that the diagnosis is kept but marked `unverified`. More detail in [docs/architecture.md](docs/architecture.md).

## Quick start

Requirements: Python 3.11 or newer, Docker. No API key is needed for replay mode.

```bash
python -m venv .venv
# activate it, then:
pip install -e ".[agents,db,embed,dev]"
cp .env.example .env          # replay is the default LLM mode

make up      # Postgres with pgvector (docker compose up -d --wait)
make seed    # generate the data and embed the runbooks into pgvector
make demo    # diagnose the sample incident from recorded model replies
make eval    # replay all five runs and check they reproduce results/ exactly
make test    # unit tests (those marked `db` are skipped)
```

On Windows without `make`, use `tasks.ps1`: `.\tasks.ps1 up`, `seed`, `demo`, `eval`, `test`, `lint`. It reads the Python command from `$env:PY` (default `python`).

Notes:

- The first run downloads the embedding model (`sentence-transformers/all-MiniLM-L6-v2`) from Hugging Face. After that it runs locally.
- `make demo` and `make eval` need the recorded replies in `data/llm_cache/` (about 245 small shard folders, 8 MB). Without them, replay mode stops with a "no recorded response" error that says how to record it.
- `make demo` needs the database to be up and seeded, because runbook search uses pgvector.
- Checked on the author's machine: `python -m incidentiq.cli diagnose --demo --llm replay` exits 0 and prints the plan, each tool call with its redacted result, the diagnosis and a passed verifier line, from the recorded cache with no network call to a model. The demo incident is a dev-split connection-pool case. The demo runs the verifier but not the v4 prompt changes (the CLI does not enable them).
- Recording new model replies (`make eval-record RUN=v1-tools SPLIT=all`) needs an API key for an OpenAI-compatible endpoint; see `.env.example`. The recordings here were made with `gemini-3.5-flash-lite` on a free tier.

## Results

Same model, same data, same scoring for every row. Only the system changes. The **test** split (25 incidents) was held out for reported numbers; **dev** (15) was used while tuning v4. Intervals are 95% Wilson intervals. Raw files: [results/comparison.md](results/comparison.md), and per run `results/<run>/results.json`, `results.md`, `traces.jsonl` and `failure_notes.json`.

<!-- BEGIN GENERATED:results (python scripts/make_readme_tables.py --write) -->
| Version | Test accuracy (95% Wilson interval) | Strict accuracy | Citation validity | Support: lexical / gold | Gold evidence recall | Gold runbook cited | LLM calls / incident | Prompt / completion tokens / incident | Dev accuracy |
|---|---|---|---|---|---|---|---|---|---|
| [v0-baseline](results/v0-baseline/results.md) | 92.0% (23/25; 75.0% to 97.8%) | 92.0% | 100.0% | 98.7% / 71.6% | 48.2% | 0.0% | 1.04 | 5556 / 365 | 93.3% (14/15) |
| [v1-tools](results/v1-tools/results.md) | 64.0% (16/25; 44.5% to 79.8%) | 64.0% | 100.0% | 89.5% / 34.7% | 31.3% | 12.0% | 6.60 | 13486 / 1699 | 73.3% (11/15) |
| [v2-retrieval](results/v2-retrieval/results.md) | 64.0% (16/25; 44.5% to 79.8%) | 64.0% | 100.0% | 87.0% / 38.0% | 33.4% | 24.0% | 6.60 | 13570 / 1742 | 73.3% (11/15) |
| [v3-verifier](results/v3-verifier/results.md) | 60.0% (15/25; 40.7% to 76.6%) | 60.0% | 100.0% | 98.0% / 36.7% | 31.4% | 24.0% | 7.36 | 15645 / 1996 | 73.3% (11/15) |
| [v4-final](results/v4-final/results.md) | 80.0% (20/25; 60.9% to 91.1%) | 80.0% | 100.0% | 98.3% / 52.5% | 53.6% | 44.0% | 7.16 | 18677 / 2064 | 80.0% (12/15) |
<!-- END GENERATED:results -->

What this table does and does not show:

- The single-call baseline (v0) scores highest on test, 92%. The synthetic logs are sparse (about 3 lines per minute) and the cause lines sit minutes from the alert, so pasting the last 100 lines is close to ceiling. v4 is not distinguishable from v0: the intervals overlap widely. **This repo does not show that the agent beats the single-call baseline.**
- v1 to v4 on test is 64% to 80% (dev: 73% to 80%). The direction is the same on both splits, but the intervals overlap, so this is not a significant difference.
- The rise in "gold runbook cited" (12% in v1 to 44% in v4) is largely produced by the v4 stopping rule that forces a runbook lookup before the planner can finish. It is not evidence of better reasoning.
- The verifier (v3) raised its own lexical support rate (87.0% in v2 to 98.0% in v3), which is partly circular: the lexical column is the verifier's own check. It did not raise accuracy, and the independent gold-ID support did not rise (38.0% to 36.7%).
- Citation validity is 100% in every run: no run cited an evidence ID it had not retrieved.
- The `scale100` condition, added because of the near-ceiling baseline above, is reported in the next section.

### The `scale100` condition (about 100 times the log volume)

Added after the original results showed the baseline near ceiling, so it was not planned before those numbers were seen. It was pre-registered ([docs/benchmark-scale100.md](docs/benchmark-scale100.md), committed before any scale100 run), and v5-scale was built and chosen on dev only ([results/scale100/TUNING_LOG.md](results/scale100/TUNING_LOG.md)). Only log volume changes: about 8,500 extra healthy-traffic lines per service per incident, from the existing noise templates. v0 is the naive baseline (last 100 log lines of the alerting service); v0b is a single call over the last 100 WARN and ERROR lines; v4-final is the recorded v4 agent unchanged; v5-scale is v4 plus a rarity-ranked log search.

<!-- BEGIN GENERATED:scale100 (python scripts/make_readme_tables.py --write) -->
| Version | Test accuracy (95% Wilson interval) | Strict accuracy | Citation validity | Support: lexical / gold | Gold evidence recall | Gold runbook cited | LLM calls / incident | Dev accuracy |
|---|---|---|---|---|---|---|---|---|
| [v0-baseline](results/scale100/v0-baseline/results.md) | 4.0% (1/25; 0.7% to 19.5%) | 0.0% | 100.0% | 85.7% / 0.0% | 0.0% | 0.0% | 1.00 | 20.0% (3/15) |
| [v0b-filtered-baseline](results/scale100/v0b-filtered-baseline/results.md) | 88.0% (22/25; 70.0% to 95.8%) | 88.0% | 100.0% | 96.7% / 80.0% | 38.2% | 0.0% | 1.00 | 93.3% (14/15) |
| [v4-final](results/scale100/v4-final/results.md) | 76.0% (19/25; 56.6% to 88.5%) | 76.0% | 100.0% | 99.2% / 46.3% | 41.3% | 44.0% | 7.28 | 86.7% (13/15) |
| [v5-scale](results/scale100/v5-scale/results.md) | 88.0% (22/25; 70.0% to 95.8%) | 84.0% | 99.4% | 94.1% / 56.3% | 61.8% | 52.0% | 6.52 | 86.7% (13/15) |
<!-- END GENERATED:scale100 -->

What this table does and does not show:

- **v5-scale ties the filtered baseline** (22/25 each, identical intervals). This repo does not show that the agent beats a baseline that filters the log dump. v5-scale's strict accuracy (84%) is slightly below v0b's (88%).
- Both are far above the naive log dump (v0: 1/25), which shows what the 100x volume does to a plain dump. It is not the right comparison for the agent, because the filtered baseline also costs one call and uses no tools.
- v5-scale (88%) and v4-final (76%) differ by 3 incidents, inside overlapping intervals. v5 was chosen over v4 on dev by a rule written beforehand, where the two tied (13/15 each, on different incidents), so this is not shown to be an improvement.
- v5-scale retrieves more of the gold evidence (61.8%, against 38.2% for v0b and 41.3% for v4) and cites the gold runbook section more often (52%; v0b has no runbook access). The lexical support column for v5 (94.1%) is the verifier's own check.
- v0b and v5-scale missed the same three incidents (INC-005, INC-009, INC-035); v4 missed those and three more (INC-029, INC-030, INC-039). Two of the three shared misses are metrics-only incidents whose evidence is in a metric the agent never queried. Per-incident notes are in `results/scale100/<run>/failure_notes.json`, written for v0b, v4 and v5 from the traces; the naive baseline's 24 misses are not annotated.
- n = 25 per run, one recording each at temperature 0, so run-to-run variation is not measured.
- During recording, the v5 test run printed its own summary table, so the v5 test score was seen before the other test results were read. No version was changed after any test result existed.

### Redaction (before the model sees anything)

<!-- BEGIN GENERATED:redaction (python scripts/make_readme_tables.py --write) -->
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
<!-- END GENERATED:redaction -->

The 100% on the injected set is optimistic: the detectors were written against the same generator that produced those items. The hand-written hard set (formats the generator does not use) is the more realistic number, and it is 59.5%. Details and the list of real misses: [docs/redaction.md](docs/redaction.md) and [results/redaction/results.md](results/redaction/results.md).

### Retrieval only (no LLM)

How often runbook search returns the gold runbook section, on all 40 incidents. `alert` is a lower bound (the alert text alone). `alert+evidence` adds the gold log lines or a description of the gold metrics. `diagnosed-fix` asks "how to mitigate and fix <true category>", so it uses the true label and is an upper bound. A section hit needs the gold section in the top k; a runbook hit needs any section of the gold runbook. Raw files: `results/retrieval/`.

<!-- BEGIN GENERATED:retrieval (python scripts/make_readme_tables.py --write) -->
| Query | Search | section@1 | section@3 | runbook@1 | runbook@3 |
|---|---|---|---|---|---|
| alert | embedding (pgvector) | 0.0% | 0.0% | 10.0% | 20.0% |
| alert | keyword (BM25) | 0.0% | 0.0% | 12.5% | 25.0% |
| alert+evidence | embedding (pgvector) | 2.5% | 30.0% | 75.0% | 80.0% |
| alert+evidence | keyword (BM25) | 7.5% | 7.5% | 62.5% | 72.5% |
| diagnosed-fix | embedding (pgvector) | 60.0% | 90.0% | 100.0% | 100.0% |
| diagnosed-fix | keyword (BM25) | 0.0% | 30.0% | 30.0% | 60.0% |
<!-- END GENERATED:retrieval -->

## How the evaluation works

- **Data.** 40 incidents, 4 per root-cause category (10 categories), 6 services, 18 runbooks. Each incident has a ground-truth category, a short statement, gold evidence IDs and a gold runbook section. Ten incidents are hard cases (one per category): logs only, metrics only, overlapping symptoms, or runbook needed to disambiguate.
- **Split.** 15 dev incidents (used while tuning) and 25 test incidents (used only for reported numbers), fixed in `data/split.json`.
- **Primary metric.** Root-cause accuracy: the predicted category equals the true one. Also reported: strict accuracy (category correct and a gold log or metric ID cited), citation validity, citation support (lexical, and gold), gold evidence recall, and cost (LLM calls, tokens). Definitions: [docs/evaluation.md](docs/evaluation.md).
- **Protocol.** Prompts and stopping rules for v4 were written from dev failures only. The test split was not run until v4 was frozen, and it was run with `--quiet`, which hides per-incident lines. `results/TUNING_LOG.md` records every change and why. After v4 was frozen, the recorded runs and the failure notes were not used to change any version.
- **Reproducibility.** `python -m incidentiq.eval --run all --split all --llm replay --check` replays all five runs from the recorded cache and fails unless `results.json`, `results.md` and `traces.jsonl` match the committed files byte for byte.
- **Tables.** The tables in this README are generated from the result files by `scripts/make_readme_tables.py`, and `tests/test_readme_tables.py` fails if the README drifts from them.

## Limitations

- **Synthetic data.** Logs and metrics are generated from templates. Log noise is template-based, which is easier than real logs.
- **Same author for data and runbooks.** The runbooks were written by the same person as the data, so they match it more closely than real runbooks would. Mitigations: loose wording in a third of the runbooks (1, 4, 5, 6, 8 and 9) and several deliberately similar ones (2, 3, 10 and 12), plus runbooks 11 to 18 that match no incident or only sound relevant. The retrieval table shows retrieval is not trivially perfect.
- **Sparse logs.** About 3 lines per minute across all services (roughly 520 to 560 lines per 3-hour incident), with the cause lines minutes from the alert. A naive log dump therefore scores near ceiling (v0: 92% on test). The `scale100` condition tests this: with 100 times the volume the naive dump falls to 4%, but a filtered dump (v0b) scores 88%, the same as the best agent (v5-scale).
- **Small benchmark.** 25 test incidents. The intervals are wide (for example 60.9% to 91.1% around 80%), and most differences between versions are inside them.
- **Regex redaction misses formats.** On the hand-written hard set it caught 25 of 42. Real misses: phone numbers without a leading `+` (`98765 43210`, `09876543210`, `(415) 555-0132`, `+44 (0)20 7946 0958`); names outside a `user=` field (4 of 5 hard-set names missed); a URL-encoded email (`%40`); cards and Aadhaar-style IDs written with dots; a PAN-style ID; an IPv6 address; passwords in a JSON dump, after a `pwd` word without `=`, after a `-p` flag, or in a `redis://:pass@` URL. See [docs/redaction.md](docs/redaction.md) for why each is missed. Separately, 119 of 20,656 clean lines were altered (0.6%), almost all of them 12-digit order references that pass the Aadhaar checksum.
- **The verifier's support check is lexical and approximate.** It grades its own homework: the "lexical" support column is the check the verifier itself applies, so it is not independent evidence of grounding. It can reject a fair statement. In four correct diagnoses (two in v3, two in v4) a statement about a metric was rejected at 14% to 27% overlap while citing that metric. It can also accept a loosely related one: a statement with a changed date still scored 62% overlap in a hand check, so dates and numbers can slip through. It checks grounding (does the cited text relate to the claim), not correctness.
- **Single free-tier model.** Everything was recorded with `gemini-3.5-flash-lite`. Results may not carry over to other models.
- **Quota shapes recording.** The free tier's daily limit meant runs were recorded in resumable pieces (live mode caches each reply and carries on the next day).

## Design decisions

- **LangGraph.** The loop has distinct steps (plan, act, observe, report, verify) with conditional edges (loop or stop, retry or end). Writing them as graph nodes keeps each one small and testable on its own, and makes the step cap and retry limit explicit in the graph rather than buried in a loop.
- **pgvector.** Runbook retrieval is the one place where dense embeddings are used, one chunk per runbook section so a citation points at exactly one section. Postgres with pgvector runs in Docker, uses an HNSW cosine index, and stores which embedding model built the table so models are never mixed.
- **Replay mode.** Model replies are recorded once, keyed by a hash of the request, and committed. Anyone can then reproduce every number offline, without a key, and CI-style checks can replay the benchmark exactly. The cost is that base prompts are frozen (`tests/test_prompts.py`): changing one makes recordings unreachable.
- **Redaction before the LLM.** PII and secrets are removed from tool output before it is stored, and again in the LLM client on every prompt and reply. A regression test checks that no injected value survives the tool-to-redaction path, and each benchmark run also checks the prompts actually sent to the model (0 leaks in every run). The measured limits are in the redaction section above.
- **Evaluation in the repo.** Every number here comes from a committed result file, so claims can be checked.

More: [docs/design-decisions.md](docs/design-decisions.md).

## Project structure

```
incidentiq/
  config.py  schemas.py  data.py  redaction.py  checksums.py  cli.py  synthetic.py  text.py
  llm/        base.py  replay.py  live.py  mock.py  cache.py     (client interface and modes)
  tools/      metrics.py  logs.py  runbooks.py  runbooks_keyword.py
  store/      db.py  embed.py  chunking.py  ingest.py            (pgvector)
  agents/     graph.py  planner.py  investigator.py (act, observe)  reporter.py
              verifier.py  prompts.py  toolbox.py  baseline.py (v0)
  eval/       __main__.py  runner.py  variants.py  metrics.py  report.py
              redaction_eval.py  redaction_hard_cases.py  retrieval_eval.py
data/         incidents/ metrics/ logs/ runbooks/ llm_cache/ split.json  (+ PII manifests)
scripts/      generate_data.py  datagen/  make_readme_tables.py
results/      v0-baseline/ ... v4-final/  scale100/  redaction/  retrieval/  TUNING_LOG.md  comparison.md
docs/         architecture.md  evaluation.md  redaction.md  design-decisions.md  benchmark-scale100.md
tests/
```

**Add a tool.** (1) Write the function in `incidentiq/tools/` returning a `ToolResult` whose evidence items have deterministic IDs. (2) Add its name to the `Tool` literal in `schemas.py`. (3) Add its allowed and required arguments and a call in `agents/toolbox.py`. (4) Describe it in the planner prompt in `agents/prompts.py`. (5) Add tests in `tests/test_tools.py`. Step 4 changes the planner prompt, which is frozen for the recorded benchmark: existing replays stop matching, so a new tool means re-recording the affected runs (or adding it behind a new variant in `eval/variants.py`).

**Add an incident or runbook.** Incidents are generated, not hand-written: edit the catalogue in `scripts/datagen/catalog.py` (causes, anomalies, telltale lines) and the runbooks in `scripts/datagen/runbooks.py`, then run `python scripts/generate_data.py` and `make seed`. Gold labels and gold evidence IDs are produced at generation time. The generator shuffles incidents with a fixed seed before numbering them, so changing the number of incidents renumbers the rest: the committed results and recordings no longer match, and `tests/test_data.py` pins the generated files. Treat a changed dataset as a new benchmark, with its own split and recordings.

## Licence

No licence file has been added yet.
