# Retrieval-only evaluation (test split)

Embedder: `sentence-transformers/all-MiniLM-L6-v2`. Section hit = a gold runbook section is in the top k; runbook hit = any section of the gold runbook is.

| Group | n | Query | section@1 | section@3 | runbook@1 | runbook@3 |
|---|---|---|---|---|---|---|
| all | 25 | alert | 0% | 0% | 12% | 20% |
| all | 25 | alert+evidence | 4% | 32% | 80% | 84% |
| all | 25 | diagnosed-fix | 68% | 92% | 100% | 100% |
| standard | 20 | alert | 0% | 0% | 10% | 20% |
| standard | 20 | alert+evidence | 5% | 35% | 85% | 90% |
| standard | 20 | diagnosed-fix | 60% | 90% | 100% | 100% |
| metrics_only | 2 | alert | 0% | 0% | 0% | 0% |
| metrics_only | 2 | alert+evidence | 0% | 0% | 50% | 50% |
| metrics_only | 2 | diagnosed-fix | 100% | 100% | 100% | 100% |
| overlapping | 1 | alert | 0% | 0% | 0% | 0% |
| overlapping | 1 | alert+evidence | 0% | 100% | 100% | 100% |
| overlapping | 1 | diagnosed-fix | 100% | 100% | 100% | 100% |
| logs_only | 1 | alert | 0% | 0% | 100% | 100% |
| logs_only | 1 | alert+evidence | 0% | 0% | 100% | 100% |
| logs_only | 1 | diagnosed-fix | 100% | 100% | 100% | 100% |
| runbook_needed | 1 | alert | 0% | 0% | 0% | 0% |
| runbook_needed | 1 | alert+evidence | 0% | 0% | 0% | 0% |
| runbook_needed | 1 | diagnosed-fix | 100% | 100% | 100% | 100% |

## Misses with alert+evidence queries (section@3): 17

- INC-001 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-6', 'R-02-1', 'R-02-2']
- INC-003 (disk_full, standard): gold ['R-06-5'], got ['R-06-3', 'R-06-4', 'R-06-6']
- INC-005 (cache_stampede_outage, metrics_only): gold ['R-10-5'], got ['R-10-6', 'R-10-3', 'R-02-1']
- INC-007 (downstream_timeout, standard): gold ['R-04-5'], got ['R-04-2', 'R-04-1', 'R-03-6']
- INC-008 (misconfiguration, standard): gold ['R-08-5'], got ['R-08-3', 'R-08-6', 'R-08-2']
- INC-009 (disk_full, metrics_only): gold ['R-06-5'], got ['R-03-6', 'R-13-4', 'R-03-2']
- INC-011 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-13-6', 'R-03-6', 'R-10-2']
- INC-018 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
- INC-027 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-2', 'R-04-2', 'R-04-3']
- INC-029 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-2', 'R-09-1', 'R-16-6']
- INC-030 (traffic_spike_rate_limit, logs_only): gold ['R-09-5'], got ['R-09-2', 'R-09-1', 'R-09-3']
- INC-031 (disk_full, standard): gold ['R-06-5'], got ['R-06-4', 'R-06-3', 'R-06-2']
- INC-032 (downstream_timeout, standard): gold ['R-04-5'], got ['R-04-2', 'R-04-6', 'R-04-1']
- INC-034 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-1', 'R-02-6', 'R-02-3']
- INC-035 (misconfiguration, runbook_needed): gold ['R-08-3', 'R-08-5'], got ['R-03-6', 'R-07-6', 'R-13-6']
- INC-038 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-2', 'R-09-4']
- INC-040 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
