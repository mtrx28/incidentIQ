# Retrieval-only evaluation (all split, keyword BM25 over section text)

Section hit = a gold runbook section is in the top k; runbook hit = any section of the gold runbook is.

| Group | n | Query | section@1 | section@3 | runbook@1 | runbook@3 |
|---|---|---|---|---|---|---|
| all | 40 | alert | 0% | 0% | 12% | 25% |
| all | 40 | alert+evidence | 8% | 8% | 62% | 72% |
| all | 40 | diagnosed-fix | 0% | 30% | 30% | 60% |
| standard | 30 | alert | 0% | 0% | 13% | 27% |
| standard | 30 | alert+evidence | 10% | 10% | 70% | 80% |
| standard | 30 | diagnosed-fix | 0% | 30% | 30% | 60% |
| metrics_only | 3 | alert | 0% | 0% | 0% | 0% |
| metrics_only | 3 | alert+evidence | 0% | 0% | 33% | 33% |
| metrics_only | 3 | diagnosed-fix | 0% | 33% | 67% | 100% |
| runbook_needed | 2 | alert | 0% | 0% | 0% | 0% |
| runbook_needed | 2 | alert+evidence | 0% | 0% | 0% | 0% |
| runbook_needed | 2 | diagnosed-fix | 0% | 0% | 0% | 0% |
| logs_only | 3 | alert | 0% | 0% | 0% | 33% |
| logs_only | 3 | alert+evidence | 0% | 0% | 33% | 67% |
| logs_only | 3 | diagnosed-fix | 0% | 33% | 0% | 33% |
| overlapping | 2 | alert | 0% | 0% | 50% | 50% |
| overlapping | 2 | alert+evidence | 0% | 0% | 100% | 100% |
| overlapping | 2 | diagnosed-fix | 0% | 50% | 50% | 100% |

## Misses with alert+evidence queries (section@3): 37

- INC-001 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-3', 'R-07-2', 'R-07-6']
- INC-002 (bad_deployment, standard): gold ['R-01-5'], got ['R-01-4', 'R-07-2', 'R-01-7']
- INC-003 (disk_full, standard): gold ['R-06-5'], got ['R-06-7', 'R-06-6', 'R-17-8']
- INC-004 (downstream_timeout, standard): gold ['R-04-5'], got ['R-07-3', 'R-17-3', 'R-07-6']
- INC-005 (cache_stampede_outage, metrics_only): gold ['R-10-5'], got ['R-10-6', 'R-10-3', 'R-03-8']
- INC-006 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-3', 'R-07-2', 'R-07-3']
- INC-007 (downstream_timeout, standard): gold ['R-04-5'], got ['R-07-3', 'R-17-3', 'R-01-7']
- INC-009 (disk_full, metrics_only): gold ['R-06-5'], got ['R-07-2', 'R-01-6', 'R-07-6']
- INC-011 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-6', 'R-10-8']
- INC-012 (expired_tls_cert, standard): gold ['R-07-5'], got ['R-07-3', 'R-07-4', 'R-18-8']
- INC-013 (slow_query_missing_index, standard): gold ['R-03-5'], got ['R-03-3', 'R-04-6', 'R-03-1']
- INC-014 (downstream_timeout, runbook_needed): gold ['R-04-3', 'R-04-5'], got ['R-17-4', 'R-07-2', 'R-01-7']
- INC-015 (memory_leak_oom, logs_only): gold ['R-05-5'], got ['R-11-3', 'R-05-8', 'R-07-2']
- INC-016 (slow_query_missing_index, standard): gold ['R-03-5'], got ['R-03-3', 'R-04-6', 'R-03-1']
- INC-017 (bad_deployment, logs_only): gold ['R-01-5'], got ['R-01-4', 'R-07-2', 'R-01-7']
- INC-018 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-05-8', 'R-07-2']
- INC-019 (db_connection_pool_exhaustion, metrics_only): gold ['R-02-5'], got ['R-07-2', 'R-01-6', 'R-07-6']
- INC-020 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-6', 'R-01-6']
- INC-022 (bad_deployment, standard): gold ['R-01-5'], got ['R-01-4', 'R-07-2', 'R-01-7']
- INC-023 (disk_full, standard): gold ['R-06-5'], got ['R-06-7', 'R-06-6', 'R-17-8']
- INC-024 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-15-3', 'R-07-2', 'R-17-4']
- INC-025 (slow_query_missing_index, overlapping): gold ['R-03-5'], got ['R-03-3', 'R-04-6', 'R-03-1']
- INC-026 (expired_tls_cert, overlapping): gold ['R-07-5'], got ['R-07-3', 'R-07-4', 'R-18-8']
- INC-027 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-15-3', 'R-02-2', 'R-17-4']
- INC-028 (expired_tls_cert, standard): gold ['R-07-5'], got ['R-07-3', 'R-07-4', 'R-18-8']
- INC-029 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-15-3', 'R-07-2', 'R-17-4']
- INC-030 (traffic_spike_rate_limit, logs_only): gold ['R-09-5'], got ['R-15-3', 'R-07-2', 'R-17-4']
- INC-031 (disk_full, standard): gold ['R-06-5'], got ['R-06-7', 'R-06-6', 'R-07-3']
- INC-032 (downstream_timeout, standard): gold ['R-04-5'], got ['R-07-3', 'R-17-3', 'R-07-6']
- INC-033 (bad_deployment, standard): gold ['R-01-5'], got ['R-01-4', 'R-07-2', 'R-01-7']
- INC-034 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-3', 'R-02-2', 'R-02-6']
- INC-035 (misconfiguration, runbook_needed): gold ['R-08-3', 'R-08-5'], got ['R-07-2', 'R-07-6', 'R-07-3']
- INC-036 (expired_tls_cert, standard): gold ['R-07-5'], got ['R-07-3', 'R-07-4', 'R-18-8']
- INC-037 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-05-8', 'R-07-2']
- INC-038 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-6', 'R-01-6']
- INC-039 (slow_query_missing_index, standard): gold ['R-03-5'], got ['R-03-3', 'R-04-6', 'R-03-1']
- INC-040 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-05-8', 'R-07-2']
