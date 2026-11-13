# v3-verifier

v2 plus the citation verifier and up to 2 reporter retries.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v3-verifier --llm replay`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 60.0% (15/25; 95% CI 40.7% to 76.6%) | 73.3% (11/15; 95% CI 48.0% to 89.1%) | 65.0% (26/40; 95% CI 49.5% to 77.9%) |
| Strict accuracy (category + cites gold cause evidence) | 60.0% (15/25) | 73.3% (11/15) | 65.0% (26/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 98.0% | 98.2% | 98.1% |
| Citation support, gold check | 36.7% | 35.1% | 36.1% |
| Gold evidence recall | 31.4% | 33.0% | 32.0% |
| Gold runbook section cited | 24.0% | 20.0% | 22.5% |
| Cause evidence retrieved at all | 72.0% | 80.0% | 75.0% |
| Tool calls per incident | 5.20 | 5.13 | 5.17 |
| LLM calls per incident | 7.36 | 7.27 | 7.33 |
| Reporter retries per incident | 0.76 | 0.47 | 0.65 |
| Prompt / completion tokens per incident | 15645 / 1996 | 15476 / 1940 | 15582 / 1975 |
| LLM latency per incident (recorded) | 72.9 s | 104.3 s | 84.7 s |
| Unverified diagnoses / failed runs / tool errors | 4 / 0 / 0 | 2 / 0 / 0 | 6 / 0 / 0 |

## Accuracy by category (test)

| Category | Correct | n |
|---|---|---|
| bad_deployment | 1 | 2 |
| cache_stampede_outage | 0 | 3 |
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
| standard | 14 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (14 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-003 | test | standard | disk_full | bad_deployment | 7 | never retrieved the cause evidence | Same calls as v2 (disk_used_pct never queried; S2 returned 0 lines). Reporter retried once, then verification passed with a claim citing R-01-1; predicted bad_deployment. |
| INC-005 | test | metrics_only | cache_stampede_outage | slow_query_missing_index | 7 | - | Same calls as v2 (M-028 never queried; S7 runbook query worded around downstream or slow query). Reporter retried twice, then verification passed; predicted slow_query_missing_index. |
| INC-009 | test | metrics_only | disk_full | downstream_timeout | 7 | never retrieved the cause evidence | Same calls and claims as v2: disk_used_pct (gold M-049) never queried; S7 runbook query worded around downstream timeout. Verification passed with no retries. |
| INC-011 | test | standard | cache_stampede_outage | slow_query_missing_index | 6 | true cause was among its hypotheses | New miss vs v2. M-021 and M-019 retrieved (S2,S4) and cache_stampede was a hypothesis, but after 2 reporter retries the claims cite M-024, L-0310, R-03-2; predicted slow_query_missing_index. |
| INC-016 | dev | standard | slow_query_missing_index | downstream_timeout | 6 | - | Same calls and claims as v2: M-024 retrieved at S1, db_pool (gold M-021) never queried, payments unchanged (S4,S5). Verification passed with no retries. |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | downstream_timeout | 7 | never retrieved the cause evidence | Same calls and claims as v2: db_pool_in_use_pct (gold M-012) never queried; S7 runbook query worded around upstream timeout. Verification passed with no retries. |
| INC-020 | dev | standard | cache_stampede_outage | downstream_timeout | 8 | hit the step cap; never retrieved the cause evidence | Same calls and claims as v2; hit the step cap (8), no db_pool or cache_hit_ratio query (gold M-012/M-010). Verification passed with no retries. |
| INC-024 | dev | standard | traffic_spike_rate_limit | downstream_timeout | 6 | never retrieved the cause evidence | Same calls and claims as v2: cpu_pct and request_rate_rps (gold M-038/M-044) never queried; inventory unchanged (S3-S5). Verification passed with no retries. |
| INC-027 | test | standard | traffic_spike_rate_limit | downstream_timeout | 5 | never retrieved the cause evidence | Same calls and claims as v2: no cpu/request-rate query (gold M-038/M-044); S3 filtered to ERROR while gold lines are WARN. Verification passed with no retries. |
| INC-030 | test | logs_only | traffic_spike_rate_limit | downstream_timeout | 4 | never retrieved the cause evidence | Same calls and claims as v2: logs-only case, S2 filtered to ERROR while gold lines are WARN/INFO; stopped after 4 steps. Verification passed with no retries. |
| INC-033 | test | standard | bad_deployment | downstream_timeout | 5 | never retrieved the cause evidence; true cause was among its hypotheses | Same calls and claims as v2: S2 returned 0 lines; gold deploy/exception lines and M-036 never retrieved. Verification passed with no retries. |
| INC-035 | test | runbook_needed | misconfiguration | downstream_timeout | 7 | true cause was among its hypotheses | Same calls as v2. Reporter retried once; claims cite M-005 and L-0285..L-0301, the action cites R-04-6; gold L-0281/L-0283 (retrieved at S2) are not cited. Predicted downstream_timeout. |
| INC-038 | test | standard | cache_stampede_outage | downstream_timeout | 6 | never retrieved the cause evidence; no runbook retrieved; unverified after retries | Same calls as v2, no runbook retrieved. After 2 reporter retries the verifier still reported no recommended actions, so the diagnosis is marked unverified. db_pool and cache_hit_ratio never queried. |
| INC-039 | test | standard | slow_query_missing_index | downstream_timeout | 6 | never retrieved the cause evidence | Same calls and claims as v2: notifications db_pool and latency (gold M-030/M-033) never queried; payments unchanged (S3,S4,S6). Verification passed with no retries. |
