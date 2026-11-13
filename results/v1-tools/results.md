# v1-tools

Plan-act-observe loop with metrics, log search and keyword (BM25) runbook search. No verifier.

Model `gemini-3.5-flash-lite`; embedder `none (BM25)`; step cap 8. Reproduce with `python -m incidentiq.eval --run v1-tools --llm replay`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 64.0% (16/25; 95% CI 44.5% to 79.8%) | 73.3% (11/15; 95% CI 48.0% to 89.1%) | 67.5% (27/40; 95% CI 52.0% to 79.9%) |
| Strict accuracy (category + cites gold cause evidence) | 64.0% (16/25) | 73.3% (11/15) | 67.5% (27/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 89.5% | 96.4% | 92.0% |
| Citation support, gold check | 34.7% | 48.2% | 39.7% |
| Gold evidence recall | 31.3% | 35.5% | 32.8% |
| Gold runbook section cited | 12.0% | 26.7% | 17.5% |
| Cause evidence retrieved at all | 72.0% | 80.0% | 75.0% |
| Tool calls per incident | 5.16 | 5.20 | 5.17 |
| LLM calls per incident | 6.60 | 6.87 | 6.70 |
| Reporter retries per incident | 0.00 | 0.00 | 0.00 |
| Prompt / completion tokens per incident | 13486 / 1699 | 14614 / 1726 | 13909 / 1709 |
| LLM latency per incident (recorded) | 89.3 s | 101.2 s | 93.8 s |
| Unverified diagnoses / failed runs / tool errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

## Accuracy by category (test)

| Category | Correct | n |
|---|---|---|
| bad_deployment | 1 | 2 |
| cache_stampede_outage | 1 | 3 |
| db_connection_pool_exhaustion | 2 | 2 |
| disk_full | 1 | 3 |
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
| standard | 15 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (13 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-003 | test | standard | disk_full | misconfiguration | 7 | never retrieved the cause evidence | disk_used_pct (gold M-031) never queried; S1,S3,S5 covered error rate, latency, restarts. S2 (ERROR, query 'error') returned 0 lines. No gold ID retrieved; claims cite M-032, L-0197, L-0244. |
| INC-005 | test | metrics_only | cache_stampede_outage | db_connection_pool_exhaustion | 7 | - | M-030 (db pool) retrieved at S6, M-028 (cache hit ratio) never queried; predicted db_connection_pool_exhaustion. S7 runbook query worded around downstream timeout or slow query; R-10-5 not retrieved. |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 7 | never retrieved the cause evidence | disk_used_pct (gold M-049) never queried; S1,S3,S5,S6 were 7-point windows (no change test). S7 runbook query was worded around downstream timeout (R-13-8). No gold ID retrieved. |
| INC-016 | dev | standard | slow_query_missing_index | downstream_timeout | 6 | - | M-024 latency jump retrieved at S1, but db_pool (gold M-021) never queried; payments checks (S4,S5) showed no change yet downstream_timeout was kept. Gold slow-query log lines not retrieved. |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | downstream_timeout | 7 | never retrieved the cause evidence | db_pool_in_use_pct (gold M-012) never queried; S1-S6 covered error rate, restarts, latency and payment-related logs. Payments error rate unchanged (S3), yet downstream_timeout was kept. |
| INC-020 | dev | standard | cache_stampede_outage | downstream_timeout | 8 | hit the step cap; never retrieved the cause evidence | Hit the step cap (8). No db_pool or cache_hit_ratio query (gold M-012/M-010); S2-S4,S6 filtered to ERROR, while gold L-0284/L-0285 are WARN. S8 runbook query was worded around downstream timeout. |
| INC-024 | dev | standard | traffic_spike_rate_limit | downstream_timeout | 6 | never retrieved the cause evidence | cpu_pct and request_rate_rps (gold M-038/M-044) never queried; inventory checks (S3-S5) showed no change yet downstream_timeout was kept. S2 filtered to ERROR; gold L-0254/L-0256 are WARN. |
| INC-027 | test | standard | traffic_spike_rate_limit | downstream_timeout | 5 | never retrieved the cause evidence | Only payments latency and error rate queried (S1,S2); no cpu/request-rate query (gold M-038/M-044). S3 filtered to ERROR; gold L-0277/L-0280 are WARN. S5 runbook query worded around downstream. |
| INC-030 | test | logs_only | traffic_spike_rate_limit | downstream_timeout | 4 | never retrieved the cause evidence | Logs-only case: gold lines (rate limit, load shedding) are WARN/INFO, S2 filtered to ERROR. Stopped after 4 steps; S4 runbook query was worded around downstream timeout. No gold ID retrieved. |
| INC-033 | test | standard | bad_deployment | downstream_timeout | 6 | never retrieved the cause evidence; true cause was among its hypotheses | S2 (ERROR, query 'error') returned 0 lines; gold deploy and exception lines (L-0281..L-0296) and restarts metric M-036 never retrieved. S5 and S6 were two similar downstream-timeout runbook queries. |
| INC-035 | test | runbook_needed | misconfiguration | downstream_timeout | 5 | - | Gold L-0281/L-0283 retrieved at S2 and bad_deployment was a hypothesis, but downstream_timeout led. M-009 (restarts) never queried; S4 payments unchanged; S5 runbook query worded around downstream. |
| INC-038 | test | standard | cache_stampede_outage | downstream_timeout | 6 | never retrieved the cause evidence; no runbook retrieved | S3 (ERROR, query 'error') returned 0 lines; db_pool and cache_hit_ratio (gold M-021/M-019) never queried. No runbook retrieved in 6 steps, so no recommended action cites a runbook. |
| INC-039 | test | standard | slow_query_missing_index | downstream_timeout | 5 | never retrieved the cause evidence | notifications db_pool and latency (gold M-030/M-033) never queried; payments checks (S3,S4) showed no change yet downstream_timeout was kept. S5 runbook query worded around downstream timeout. |
