# v0-baseline

Single LLM call with the alert and a dump of the last 100 log lines. No tools, no plan loop, no runbooks.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v0-baseline --llm replay --condition scale100`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 4.0% (1/25; 95% CI 0.7% to 19.5%) | 20.0% (3/15; 95% CI 7.0% to 45.2%) | 10.0% (4/40; 95% CI 4.0% to 23.1%) |
| Strict accuracy (category + cites gold cause evidence) | 0.0% (0/25) | 0.0% (0/15) | 0.0% (0/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 85.7% | 84.2% | 85.2% |
| Citation support, gold check | 0.0% | 0.0% | 0.0% |
| Gold evidence recall | 0.0% | 0.0% | 0.0% |
| Gold runbook section cited | 0.0% | 0.0% | 0.0% |
| Cause evidence retrieved at all | 0.0% | 0.0% | 0.0% |
| Tool calls per incident | 0.00 | 0.00 | 0.00 |
| LLM calls per incident | 1.00 | 1.00 | 1.00 |
| Reporter retries per incident | 0.00 | 0.00 | 0.00 |
| Prompt / completion tokens per incident | 5375 / 253 | 5384 / 229 | 5378 / 244 |
| LLM latency per incident (recorded) | 2.0 s | 2.0 s | 2.0 s |
| Unverified diagnoses / failed runs / tool errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

## Accuracy by category (test)

| Category | Correct | n |
|---|---|---|
| bad_deployment | 0 | 2 |
| cache_stampede_outage | 0 | 3 |
| db_connection_pool_exhaustion | 0 | 2 |
| disk_full | 0 | 3 |
| downstream_timeout | 0 | 2 |
| expired_tls_cert | 0 | 3 |
| memory_leak_oom | 0 | 2 |
| misconfiguration | 0 | 3 |
| slow_query_missing_index | 1 | 2 |
| traffic_spike_rate_limit | 0 | 3 |

## Accuracy by case type (test)

| Case | Correct | n |
|---|---|---|
| logs_only | 0 | 1 |
| metrics_only | 0 | 2 |
| overlapping | 0 | 1 |
| runbook_needed | 0 | 1 |
| standard | 1 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (36 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-001 | test | standard | db_connection_pool_exhaustion | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-002 | dev | standard | bad_deployment | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-003 | test | standard | disk_full | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-004 | dev | standard | downstream_timeout | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-005 | test | metrics_only | cache_stampede_outage | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-006 | dev | standard | db_connection_pool_exhaustion | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-007 | test | standard | downstream_timeout | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-008 | test | standard | misconfiguration | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-009 | test | metrics_only | disk_full | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-010 | test | standard | misconfiguration | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-011 | test | standard | cache_stampede_outage | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-012 | test | standard | expired_tls_cert | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-015 | dev | logs_only | memory_leak_oom | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-017 | dev | logs_only | bad_deployment | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-018 | test | standard | memory_leak_oom | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-019 | dev | metrics_only | db_connection_pool_exhaustion | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-020 | dev | standard | cache_stampede_outage | bad_deployment | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-021 | dev | standard | misconfiguration | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-022 | test | standard | bad_deployment | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-023 | dev | standard | disk_full | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-024 | dev | standard | traffic_spike_rate_limit | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-026 | test | overlapping | expired_tls_cert | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-027 | test | standard | traffic_spike_rate_limit | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-028 | test | standard | expired_tls_cert | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-029 | test | standard | traffic_spike_rate_limit | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-030 | test | logs_only | traffic_spike_rate_limit | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-031 | test | standard | disk_full | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-032 | test | standard | downstream_timeout | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-033 | test | standard | bad_deployment | traffic_spike_rate_limit | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-034 | test | standard | db_connection_pool_exhaustion | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-035 | test | runbook_needed | misconfiguration | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-036 | dev | standard | expired_tls_cert | downstream_timeout | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-037 | dev | standard | memory_leak_oom | bad_deployment | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-038 | test | standard | cache_stampede_outage | slow_query_missing_index | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-039 | test | standard | slow_query_missing_index | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
| INC-040 | test | standard | memory_leak_oom | misconfiguration | 0 | never retrieved the cause evidence | (not yet analysed) |
