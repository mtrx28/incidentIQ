# Runbook 10: Cache outage and cache stampede

## 1. Summary

The cache in front of a service became unavailable or was emptied, so every request now goes to the database instead. The database can saturate under the extra load and start making requests wait.

## 2. Symptoms

Requests wait on the database and time out, with latency climbing and errors following. Logs mention database fallbacks and timeouts. The cache servers may refuse connections, and a sudden burst of identical lookups can appear for the same few keys.

## 3. How to confirm

Check the cache hit ratio: it falls from around ninety percent to near zero first, and the database connection usage rises after it. Search the logs for refused connections to the cache, fallbacks to the database and bursts of concurrent loads for one key. The cache drop coming first separates this from a database problem.

## 4. Likely causes

A cache node that crashed or restarted, an eviction storm, many keys expiring at the same moment, or a release that changed how keys are named so the old entries are never found.

## 5. Mitigation

Restore the cache first by restarting or failing over the node. Then protect the database by turning on request coalescing or limiting how many cache misses may load at once, and warm the hottest keys gradually. Do not restart the application while the cache is down.

## 6. Verify recovery

The cache hit ratio should recover above eighty-five percent, database connection use should fall away and latency should return to normal. Watch the database closely while the cache refills, since a second stampede is possible.

## 7. Escalation

Call the cache platform team if the cluster cannot be restored within fifteen minutes, or if data in the cache cannot be rebuilt from the source of truth quickly enough.

## 8. Related runbooks

If the database is slow while the cache is healthy, use the slow query or connection pool runbooks. The cache runbook covers what to do first; those cover the database side.
