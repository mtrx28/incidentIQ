# Runbook 02: Database connection pool exhaustion

## 1. Summary

Requests to the database are waiting. The service has used up its whole allowance of database connections, so new work queues for a free connection and eventually times out before it ever reaches the database.

## 2. Symptoms

Latency climbs and errors follow as requests wait on the database and time out. Logs mention database timeouts and requests waiting. The service's CPU stays normal because it is idle while it waits, which can make the service look healthy from the outside.

## 3. How to confirm

Check how much of the connection pool is in use: it sits at or very near its maximum. Look for log lines saying a connection is not available or that the pool is exhausted, with many requests waiting. Then look at individual queries: if they are quick and the delay is the wait for a connection, this is pool exhaustion.

## 4. Likely causes

Connections held for too long or never given back, more concurrent work than the pool was sized for, a pool maximum set too low after a change, or a stall in the database that stops connections being returned promptly.

## 5. Mitigation

Restart the affected instances to release held connections as a first step. Then raise the pool maximum, staying inside the database's own connection limit, and shed non-essential traffic. If connections are leaking, find the code path that does not return them.

## 6. Verify recovery

Pool usage should fall well below its maximum, the number of waiting requests should drop to zero and latency should return to normal within a few minutes. Watch it for half an hour in case the pool fills again.

## 7. Escalation

Call the database team if the database itself is close to its connection limit or is refusing new connections, since raising pool sizes elsewhere will then make things worse. Share the pool graphs so they can see which services hold the most connections.

## 8. Related runbooks

If one query is simply taking seconds, use the slow query runbook. If pool use rises slowly over days, use the connection leak audit. If a cache failed first, use the cache runbook.
