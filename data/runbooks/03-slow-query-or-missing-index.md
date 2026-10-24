# Runbook 03: Slow query or missing index

## 1. Summary

Requests to the database are slow. A query that used to be fast now takes seconds, usually because an index is missing or is no longer being used, and every request that depends on that query waits for it.

## 2. Symptoms

Latency climbs and errors follow as requests wait on the database and time out. Logs mention database timeouts and slow queries. The connection pool may fill as a side effect, because every connection is busy running the slow statement for longer than usual.

## 3. How to confirm

Search the logs for slow query warnings and for query plans showing a full scan of a large table. Check whether a schema migration recently dropped or changed an index. The slowness is present at normal traffic, and a single query taking several seconds is the signature, rather than short queries waiting for a connection.

## 4. Likely causes

An index that was dropped or never created, out-of-date table statistics, a code change that no longer uses the index, or a table that has grown past what the old plan can handle. Recent migrations are the first place to look.

## 5. Mitigation

Recreate the missing index using a concurrent build so writes are not blocked, then refresh the table statistics. As a stopgap, cancel the long-running queries and add a statement timeout. Revert the migration that removed the index if one is found.

## 6. Verify recovery

The slow query should disappear from the logs, its run time should return to milliseconds and request latency should recover. Check the connection pool afterwards to confirm it has drained back to normal.

## 7. Escalation

Talk to the database team before building an index on a very large table during peak hours, since the build itself adds load and can take a long time to finish.

## 8. Related runbooks

If queries are quick but requests wait for connections, use the pool exhaustion runbook. If the database is overloaded because the cache failed, use the cache runbook. If pool use rises slowly over days instead, use the connection leak audit.
