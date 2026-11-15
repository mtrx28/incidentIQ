# v4-final

v3 plus prompt and stopping-rule refinements written from dev-split failures only.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v4-final --llm replay --condition scale100`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 76.0% (19/25; 95% CI 56.6% to 88.5%) | 86.7% (13/15; 95% CI 62.1% to 96.3%) | 80.0% (32/40; 95% CI 65.2% to 89.5%) |
| Strict accuracy (category + cites gold cause evidence) | 76.0% (19/25) | 86.7% (13/15) | 80.0% (32/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 99.2% | 97.4% | 98.5% |
| Citation support, gold check | 46.3% | 60.5% | 51.8% |
| Gold evidence recall | 41.3% | 54.2% | 46.2% |
| Gold runbook section cited | 44.0% | 66.7% | 52.5% |
| Cause evidence retrieved at all | 80.0% | 93.3% | 85.0% |
| Tool calls per incident | 5.44 | 5.67 | 5.53 |
| LLM calls per incident | 7.28 | 7.67 | 7.42 |
| Reporter retries per incident | 0.56 | 0.67 | 0.60 |
| Prompt / completion tokens per incident | 24424 / 2215 | 23843 / 2261 | 24206 / 2232 |
| LLM latency per incident (recorded) | 15.7 s | 69.4 s | 35.9 s |
| Unverified diagnoses / failed runs / tool errors | 1 / 0 / 0 | 3 / 0 / 0 | 4 / 0 / 0 |

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
| slow_query_missing_index | 1 | 2 |
| traffic_spike_rate_limit | 1 | 3 |

## Accuracy by case type (test)

| Case | Correct | n |
|---|---|---|
| logs_only | 0 | 1 |
| metrics_only | 0 | 2 |
| overlapping | 1 | 1 |
| runbook_needed | 0 | 1 |
| standard | 18 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (8 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-005 | test | metrics_only | cache_stampede_outage | downstream_timeout | 6 | never retrieved the cause evidence | Metrics-only case. Queried error rate and memory on the alerting service and error rate and latency on payments; cache hit ratio (gold M-028) and db pool (M-030) were never queried. The one log search matched 64 lines, none gold. The runbook query was written around downstream_timeout. |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 5 | never retrieved the cause evidence | Metrics-only case. Queried error rate, cpu and memory; disk_used_pct (gold M-049) never queried. The one log search (954 matches, 30 shown) held no gold line. The runbook query was written around downstream_timeout. |
| INC-014 | dev | runbook_needed | downstream_timeout | bad_deployment | 6 | never retrieved the cause evidence; true cause was among its hypotheses | (not yet analysed) |
| INC-021 | dev | standard | misconfiguration | memory_leak_oom | 7 | - | (not yet analysed) |
| INC-029 | test | standard | traffic_spike_rate_limit | downstream_timeout | 5 | never retrieved the cause evidence | Standard case. The 30 lines shown from 748 matches (20-minute window, no query) held none of the gold lines (L-0278, L-0279, L-0281); metrics queried were error rate, restarts and latency, not the gold metrics M-002/M-008. The runbook query was about downstream_timeout. |
| INC-030 | test | logs_only | traffic_spike_rate_limit | slow_query_missing_index | 8 | hit the step cap; never retrieved the cause evidence | Logs-only case; hit the step cap (8). Two log searches with deploy/config/tls/timeout-style query terms matched 85 and 37 lines, none gold (L-0257, L-0261, L-0266). Final runbook query was written around slow_query_missing_index; predicted that. |
| INC-035 | test | runbook_needed | misconfiguration | bad_deployment | 6 | true cause was among its hypotheses | Gold M-009 (restarts) was retrieved at S2, but the log search (70 matches) held neither gold line (L-0281, L-0283). A second search for OOM terms returned 0 lines. The runbook query was written around bad_deployment (best match R-01-3, similarity 0.65). |
| INC-039 | test | standard | slow_query_missing_index | downstream_timeout | 6 | never retrieved the cause evidence | Standard case. The log search (956 matches, 30 shown, no query) held no gold line (L-0283, L-0303, L-0306); metrics queried were error rate, restarts and payments, not the gold metrics M-030/M-033. The runbook query was about downstream_timeout. |
