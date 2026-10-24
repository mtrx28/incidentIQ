# Retrieval-only evaluation (dev split)

Embedder: `sentence-transformers/all-MiniLM-L6-v2`. Section hit = a gold runbook section is in the top k; runbook hit = any section of the gold runbook is.

| Group | n | Query | section@1 | section@3 | runbook@1 | runbook@3 |
|---|---|---|---|---|---|---|
| all | 15 | alert | 0% | 0% | 7% | 20% |
| all | 15 | alert+evidence | 0% | 27% | 67% | 73% |
| all | 15 | diagnosed-fix | 47% | 87% | 100% | 100% |
| standard | 10 | alert | 0% | 0% | 0% | 10% |
| standard | 10 | alert+evidence | 0% | 30% | 70% | 80% |
| standard | 10 | diagnosed-fix | 60% | 90% | 100% | 100% |
| runbook_needed | 1 | alert | 0% | 0% | 100% | 100% |
| runbook_needed | 1 | alert+evidence | 0% | 0% | 100% | 100% |
| runbook_needed | 1 | diagnosed-fix | 0% | 100% | 100% | 100% |
| logs_only | 2 | alert | 0% | 0% | 0% | 0% |
| logs_only | 2 | alert+evidence | 0% | 0% | 0% | 0% |
| logs_only | 2 | diagnosed-fix | 0% | 50% | 100% | 100% |
| metrics_only | 1 | alert | 0% | 0% | 0% | 0% |
| metrics_only | 1 | alert+evidence | 0% | 0% | 100% | 100% |
| metrics_only | 1 | diagnosed-fix | 0% | 100% | 100% | 100% |
| overlapping | 1 | alert | 0% | 0% | 0% | 100% |
| overlapping | 1 | alert+evidence | 0% | 100% | 100% | 100% |
| overlapping | 1 | diagnosed-fix | 100% | 100% | 100% | 100% |

## Misses with alert+evidence queries (section@3): 11

- INC-002 (bad_deployment, standard): gold ['R-01-5'], got ['R-03-6', 'R-13-4', 'R-13-6']
- INC-004 (downstream_timeout, standard): gold ['R-04-5'], got ['R-09-1', 'R-04-2', 'R-02-1']
- INC-006 (db_connection_pool_exhaustion, standard): gold ['R-02-5'], got ['R-02-6', 'R-03-6', 'R-02-1']
- INC-014 (downstream_timeout, runbook_needed): gold ['R-04-3', 'R-04-5'], got ['R-04-1', 'R-04-2', 'R-04-6']
- INC-015 (memory_leak_oom, logs_only): gold ['R-05-5'], got ['R-11-3', 'R-11-4', 'R-11-1']
- INC-017 (bad_deployment, logs_only): gold ['R-01-5'], got ['R-03-6', 'R-13-4', 'R-13-6']
- INC-019 (db_connection_pool_exhaustion, metrics_only): gold ['R-02-5'], got ['R-02-6', 'R-12-6', 'R-02-2']
- INC-020 (cache_stampede_outage, standard): gold ['R-10-5'], got ['R-10-3', 'R-10-2', 'R-10-6']
- INC-023 (disk_full, standard): gold ['R-06-5'], got ['R-06-4', 'R-06-2', 'R-06-3']
- INC-024 (traffic_spike_rate_limit, standard): gold ['R-09-5'], got ['R-09-1', 'R-09-2', 'R-04-2']
- INC-037 (memory_leak_oom, standard): gold ['R-05-5'], got ['R-11-3', 'R-11-1', 'R-11-4']
