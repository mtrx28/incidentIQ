# v0b-filtered-baseline

Single LLM call with the alert and the last 100 WARN and ERROR log lines of the alerting service. Added for the scale100 condition; the first baseline is v0a.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v0b-filtered-baseline --llm replay --condition scale100`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 88.0% (22/25; 95% CI 70.0% to 95.8%) | 93.3% (14/15; 95% CI 70.2% to 98.8%) | 90.0% (36/40; 95% CI 77.0% to 96.0%) |
| Strict accuracy (category + cites gold cause evidence) | 88.0% (22/25) | 93.3% (14/15) | 90.0% (36/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 96.7% | 100.0% | 98.0% |
| Citation support, gold check | 80.0% | 79.0% | 79.6% |
| Gold evidence recall | 38.2% | 41.2% | 39.3% |
| Gold runbook section cited | 0.0% | 0.0% | 0.0% |
| Cause evidence retrieved at all | 92.0% | 93.3% | 92.5% |
| Tool calls per incident | 0.00 | 0.00 | 0.00 |
| LLM calls per incident | 1.00 | 1.00 | 1.00 |
| Reporter retries per incident | 0.00 | 0.00 | 0.00 |
| Prompt / completion tokens per incident | 5498 / 311 | 5685 / 328 | 5568 / 317 |
| LLM latency per incident (recorded) | 2.2 s | 1.9 s | 2.1 s |
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

## Failures (4 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-005 | test | metrics_only | cache_stampede_outage | downstream_timeout | 0 | never retrieved the cause evidence | Metrics-only case: the gold evidence is metrics (cache hit ratio M-028, db pool M-030) and a log dump holds none of it; the baseline predicted downstream_timeout from the WARN/ERROR lines. |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 0 | never retrieved the cause evidence | Metrics-only case: the gold evidence is the disk-usage metric (M-049); the log dump holds none of it; predicted downstream_timeout. |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-035 | test | runbook_needed | misconfiguration | downstream_timeout | 0 | - | Gold lines L-0281 and L-0283 were in the dump (cause evidence present), but the predicted category was downstream_timeout, not misconfiguration; no runbook was available to this variant. |
