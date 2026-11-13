# v0-baseline

Single LLM call with the alert and a dump of the last 100 log lines. No tools, no plan loop, no runbooks.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v0-baseline --llm replay`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 92.0% (23/25; 95% CI 75.0% to 97.8%) | 93.3% (14/15; 95% CI 70.2% to 98.8%) | 92.5% (37/40; 95% CI 80.1% to 97.4%) |
| Strict accuracy (category + cites gold cause evidence) | 92.0% (23/25) | 93.3% (14/15) | 92.5% (37/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 98.7% | 100.0% | 99.2% |
| Citation support, gold check | 71.6% | 76.7% | 73.5% |
| Gold evidence recall | 48.2% | 50.6% | 49.1% |
| Gold runbook section cited | 0.0% | 0.0% | 0.0% |
| Cause evidence retrieved at all | 92.0% | 93.3% | 92.5% |
| Tool calls per incident | 0.00 | 0.00 | 0.00 |
| LLM calls per incident | 1.04 | 1.00 | 1.02 |
| Reporter retries per incident | 0.00 | 0.00 | 0.00 |
| Prompt / completion tokens per incident | 5556 / 365 | 5355 / 335 | 5480 / 354 |
| LLM latency per incident (recorded) | 17.3 s | 13.4 s | 15.9 s |
| Unverified diagnoses / failed runs / tool errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

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
| misconfiguration | 3 | 3 |
| slow_query_missing_index | 2 | 2 |
| traffic_spike_rate_limit | 3 | 3 |

## Accuracy by case type (test)

| Case | Correct | n |
|---|---|---|
| logs_only | 1 | 1 |
| metrics_only | 0 | 2 |
| overlapping | 1 | 1 |
| runbook_needed | 1 | 1 |
| standard | 20 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (3 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-005 | test | metrics_only | cache_stampede_outage | downstream_timeout | 0 | never retrieved the cause evidence | Baseline sees only the last 100 log lines; gold cause evidence is metrics M-028/M-030, not in the dump. Its 4 claims cite generic 5xx lines (L-0271..L-0287); predicted downstream_timeout. |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 0 | never retrieved the cause evidence | Baseline sees only log lines; gold cause evidence is metric M-049 (disk_used_pct), not in the dump. Its 2 claims cite 503/failure lines (L-0301..L-0308); ruled_out lists disk_full. |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | downstream_timeout | 0 | never retrieved the cause evidence | Baseline sees only log lines; gold cause evidence is metric M-012 (db_pool_in_use_pct), not in the dump. Its one claim cites 503 line L-0278; ruled_out lists db_connection_pool_exhaustion. |
