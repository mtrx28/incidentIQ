# Runbook 12: Database connection leak audit

## 1. Summary

A planned procedure for finding application code that fails to give database connections back to the pool, so that requests end up waiting. Use it for slow, recurring pool growth over days, not for an acute outage in progress.

## 2. Symptoms

Connection pool usage creeps upward over days and only falls after a restart. Requests occasionally wait on the database and time out near the end of each cycle, but there is no sudden event and no clear start time to point at.

## 3. How to confirm

Switch on the pool's leak detection with a threshold of sixty seconds and read the stack traces it logs for connections held too long. Compare pool usage across several weeks to see the slow upward drift and the drops at each restart.

## 4. Likely causes

Code paths that open a connection and do not close it when an error occurs, transactions that stay open far too long, cursors that are forgotten, or background tasks that hold a connection while waiting on something slow.

## 5. Mitigation

Fix the code path that leaks and make sure connections are always closed, for example with automatic resource handling. This is a development task, not an incident response. If there is an active outage, restart instances and use the pool exhaustion runbook.

## 6. Verify recovery

Pool usage should stay flat over several days with no restarts needed, and the leak detector should stop reporting connections held beyond the threshold in the logs. Compare the new weekly graph with the one from before the fix to be sure.

## 7. Escalation

Raise a ticket with the owning team and attach the stack traces. No paging is needed, since this is slow-moving, unless the pool is already close to full right now.

## 8. Related runbooks

For an acute outage with all connections in use, use the connection pool exhaustion runbook. For one very slow query, use the slow query runbook. This audit is only for slow drift, so do not start it during an incident.
