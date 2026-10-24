# Retrieval-only evaluation (all split)

Embedder: `sentence-transformers/all-MiniLM-L6-v2`. Section hit = a gold runbook section is in the top k; runbook hit = any section of the gold runbook is.

| Group | n | Query | section@1 | section@3 | runbook@1 | runbook@3 |
|---|---|---|---|---|---|---|
| all | 40 | alert | 0% | 0% | 10% | 20% |
| all | 40 | alert+evidence | 2% | 30% | 75% | 80% |
| all | 40 | diagnosed-fix | 60% | 90% | 100% | 100% |
| standard | 30 | alert | 0% | 0% | 7% | 17% |
| standard | 30 | alert+evidence | 3% | 33% | 80% | 87% |
| standard | 30 | diagnosed-fix | 60% | 90% | 100% | 100% |
| metrics_only | 3 | alert | 0% | 0% | 0% | 0% |
| metrics_only | 3 | alert+evidence | 0% | 0% | 67% | 67% |
| metrics_only | 3 | diagnosed-fix | 67% | 100% | 100% | 100% |
| runbook_needed | 2 | alert | 0% | 0% | 50% | 50% |
| runbook_needed | 2 | alert+evidence | 0% | 0% | 50% | 50% |
| runbook_needed | 2 | diagnosed-fix | 50% | 100% | 100% | 100% |
| logs_only | 3 | alert | 0% | 0% | 33% | 33% |
| logs_only | 3 | alert+evidence | 0% | 0% | 33% | 33% |
| logs_only | 3 | diagnosed-fix | 33% | 67% | 100% | 100% |
| overlapping | 2 | alert | 0% | 0% | 0% | 50% |
| overlapping | 2 | alert+evidence | 0% | 100% | 100% | 100% |
| overlapping | 2 | diagnosed-fix | 100% | 100% | 100% | 100% |

## Misses with alert+evidence queries (section@3): 28

- INC-001 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-6', 'R-02-1', 'R-02-2']
- INC-002 (bad_deployment, standard): gold ['R-01-5'], got ['R-03-6', 'R-13-4', 'R-13-6']
- INC-003 (disk_full, standard): gold ['R-06-5'], got ['R-06-3', 'R-06-4', 'R-06-6']
- INC-004 (downstream_timeout, standard): gold ['R-04-5'], got ['R-09-1', 'R-04-2', 'R-02-1']
- INC-005 (cache_stampede_outage, metrics_only): gold ['R-10-5'], got ['R-10-6', 'R-10-3', 'R-02-1']
- INC-006 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-6', 'R-03-6', 'R-02-1']
- INC-007 (downstream_timeout, standard): gold ['R-04-5'], got ['R-04-2', 'R-04-1', 'R-03-6']
- INC-008 (misconfiguration, standard): gold ['R-08-5'], got ['R-08-3', 'R-08-6', 'R-08-2']
- INC-009 (disk_full, metrics_only): gold ['R-06-5'], got ['R-03-6', 'R-13-4', 'R-03-2']
- INC-011 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-13-6', 'R-03-6', 'R-10-2']
- INC-014 (downstream_timeout, runbook_needed): gold ['R-04-3', 'R-04-5'], got ['R-04-1', 'R-04-2', 'R-04-6']
- INC-015 (memory_leak_oom, logs_only): gold ['R-05-5'], got ['R-11-3', 'R-11-4', 'R-11-1']
- INC-017 (bad_deployment, logs_only): gold ['R-01-5'], got ['R-03-6', 'R-13-4', 'R-13-6']
- INC-018 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
- INC-019 (db_connection_pool_exhaustion, metrics_only): gold ['R-02-5'], got ['R-02-6', 'R-12-6', 'R-02-2']
- INC-020 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-2', 'R-10-6']
- INC-023 (disk_full, standard): gold ['R-06-5'], got ['R-06-4', 'R-06-2', 'R-06-3']
- INC-024 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-1', 'R-09-2', 'R-04-2']
- INC-027 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-2', 'R-04-2', 'R-04-3']
- INC-029 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-2', 'R-09-1', 'R-16-6']
- INC-030 (traffic_spike_rate_limit, logs_only): gold ['R-09-5'], got ['R-09-2', 'R-09-1', 'R-09-3']
- INC-031 (disk_full, standard): gold ['R-06-5'], got ['R-06-4', 'R-06-3', 'R-06-2']
- INC-032 (downstream_timeout, standard): gold ['R-04-5'], got ['R-04-2', 'R-04-6', 'R-04-1']
- INC-034 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-1', 'R-02-6', 'R-02-3']
- INC-035 (misconfiguration, runbook_needed): gold ['R-08-3', 'R-08-5'], got ['R-03-6', 'R-07-6', 'R-13-6']
- INC-037 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
- INC-038 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-2', 'R-09-4']
- INC-040 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
