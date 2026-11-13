# v4-final

v3 plus prompt and stopping-rule refinements written from dev-split failures only.

Model `gemini-3.5-flash-lite`; embedder `sentence-transformers/all-MiniLM-L6-v2`; step cap 8. Reproduce with `python -m incidentiq.eval --run v4-final --llm replay`.

The **test** split (25 incidents) is the held-out set used for reported numbers; **dev** (15) was used while tuning. With these sample sizes the confidence intervals are wide.

| Metric | test | dev | all |
|---|---|---|---|
| Incidents | 25 | 15 | 40 |
| Accuracy | 80.0% (20/25; 95% CI 60.9% to 91.1%) | 80.0% (12/15; 95% CI 54.8% to 93.0%) | 80.0% (32/40; 95% CI 65.2% to 89.5%) |
| Strict accuracy (category + cites gold cause evidence) | 80.0% (20/25) | 80.0% (12/15) | 80.0% (32/40) |
| Citation validity (cited IDs that exist) | 100.0% | 100.0% | 100.0% |
| Citation support, lexical check | 98.3% | 100.0% | 99.0% |
| Citation support, gold check | 52.5% | 61.9% | 56.4% |
| Gold evidence recall | 53.6% | 62.7% | 57.0% |
| Gold runbook section cited | 44.0% | 73.3% | 55.0% |
| Cause evidence retrieved at all | 88.0% | 93.3% | 90.0% |
| Tool calls per incident | 5.44 | 5.80 | 5.58 |
| LLM calls per incident | 7.16 | 7.40 | 7.25 |
| Reporter retries per incident | 0.60 | 0.40 | 0.53 |
| Prompt / completion tokens per incident | 18677 / 2064 | 18778 / 2201 | 18715 / 2116 |
| LLM latency per incident (recorded) | 17.6 s | 116.8 s | 54.8 s |
| Unverified diagnoses / failed runs / tool errors | 3 / 0 / 0 | 0 / 0 / 0 | 3 / 0 / 0 |

## Accuracy by category (test)

| Category | Correct | n |
|---|---|---|
| bad_deployment | 2 | 2 |
| cache_stampede_outage | 2 | 3 |
| db_connection_pool_exhaustion | 2 | 2 |
| disk_full | 1 | 3 |
| downstream_timeout | 2 | 2 |
| expired_tls_cert | 3 | 3 |
| memory_leak_oom | 2 | 2 |
| misconfiguration | 2 | 3 |
| slow_query_missing_index | 2 | 2 |
| traffic_spike_rate_limit | 2 | 3 |

## Accuracy by case type (test)

| Case | Correct | n |
|---|---|---|
| logs_only | 0 | 1 |
| metrics_only | 0 | 2 |
| overlapping | 1 | 1 |
| runbook_needed | 0 | 1 |
| standard | 19 | 20 |

## Redaction

Prompt-leak check for this run: **0** injected PII values found in prompts sent to the model.
Redactor on the injected set: 601/601 caught (100.0%); on the independent hard set: 25/42 (59.5%); clean lines altered: 119/20656 (0.6%). Details: `results/redaction/results.md`.

## Failures (8 of 40 incidents)

`Signals` are mechanical hints; `Reason` is written by hand from the trace (`failure_notes.json`).

| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |
|---|---|---|---|---|---|---|---|
| INC-005 | test | metrics_only | cache_stampede_outage | db_connection_pool_exhaustion | 7 | - | M-030 (db pool) retrieved at S6, M-028 (cache hit ratio) never queried; predicted db_connection_pool_exhaustion. S7 runbook query was built around db pool (R-02-1 first), so R-10-5 not retrieved. |
| INC-009 | test | metrics_only | disk_full | bad_deployment | 5 | never retrieved the cause evidence | disk_used_pct (gold M-049) never queried (S1-S3 were error rate, cpu, memory); S5 runbook query worded around bad deployment; ruled_out lists disk_full; actions cite R-01-5. |
| INC-014 | dev | runbook_needed | downstream_timeout | bad_deployment | 6 | never retrieved the cause evidence; true cause was among its hypotheses | S4,S5 checked inventory; gold M-002/M-006 are auth metrics. S6 runbook query, likely the forced v4 lookup, was built from the bad_deployment hypothesis (R-01-3). No gold ID retrieved. |
| INC-020 | dev | standard | cache_stampede_outage | db_connection_pool_exhaustion | 8 | hit the step cap; true cause was among its hypotheses | Hit the step cap (8). M-012 (db pool) retrieved at S4 and L-0284 (cache miss) at S7, and cache_stampede was a hypothesis; cache_hit_ratio (gold M-010) never queried. |
| INC-021 | dev | standard | misconfiguration | memory_leak_oom | 7 | - | Restarts rose at 07:40 (S3, gold M-018), but log queries S4,S6 returned 0 lines, so config-reload lines (gold L-0250..L-0255) not retrieved. memory_pct unchanged (S5), yet predicted memory_leak_oom. |
| INC-030 | test | logs_only | traffic_spike_rate_limit | bad_deployment | 6 | never retrieved the cause evidence | Logs-only case: gold lines (rate limit, load shedding) are WARN/INFO and not retrieved; S3,S4 queries matched 1 and 2 lines. S6 runbook query worded around bad deployment (R-01-1, similarity 0.55). |
| INC-031 | test | standard | disk_full | downstream_timeout | 7 | never retrieved the cause evidence | disk_used_pct (gold M-049) never queried; log queries S3,S6 used deploy/config/error/timeout terms, none of the gold disk lines (L-0236, L-0259, L-0263) retrieved. S7 runbook query: downstream. |
| INC-035 | test | runbook_needed | misconfiguration | bad_deployment | 7 | true cause was among its hypotheses | Gold M-009 (S2), L-0281/L-0283 (S7) and R-08-3 (S6) were retrieved, and misconfiguration was a hypothesis, but the diagnosis is bad_deployment and the action cites R-01-1. |
