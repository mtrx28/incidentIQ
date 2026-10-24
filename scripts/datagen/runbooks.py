"""Runbook content. Rendered to data/runbooks/NN-slug.md, one chunk per `##` section.

Every runbook has the same 8 sections so section IDs are predictable: R-<NN>-<section>.
Section 3 is "How to confirm" and section 5 is "Mitigation". Each section is at least 30 words, so
it can be embedded as its own chunk (no merging, which keeps citations precise).

Runbooks 1-10 match the 10 root causes. 11-12 are near-misses that sound relevant but cover a
different situation. 13-18 match no incident (they test retrieval precision).

Difficulty built in on purpose:
  * Runbooks 1, 4, 5, 6, 8 and 9 (a third of the set) describe symptoms and checks in loose
    operational language, without metric names or exact log strings.
  * Runbooks 2, 3, 10 and 12 share vocabulary (database, waiting, timing out, connections), so
    retrieval has to pick the right one.
The runbooks were still written by the same author as the data, so they match it more closely than
real ones would; the README says so.
"""

SECTIONS = [
    "Summary", "Symptoms", "How to confirm", "Likely causes",
    "Mitigation", "Verify recovery", "Escalation", "Related runbooks",
]
CONFIRM = 3
MITIGATION = 5

# (number, title, [8 section bodies in SECTIONS order])
RUNBOOKS: list[tuple[int, str, list[str]]] = [
    # --- 1: loose language ---------------------------------------------------------------
    (1, "Bad deployment or regression", [
        "A new version of a service went out and something in it does not work. This is the most "
        "common reason for a sudden, lasting rise in failures, and it is usually fixed fastest by "
        "undoing the change rather than by investigating on the live system.",
        "Things go wrong shortly after a rollout. Customers start seeing failures, dashboards turn "
        "red around the time the new version went out, and the problem does not fade by itself. "
        "The service may also restart a few times while the new version rolls through.",
        "Line the start of the trouble up against the release timeline. If it began just after a "
        "rollout and the previous version was healthy, suspect the release. Look at what the "
        "service wrote to its logs while the new version was starting and when the first failures "
        "arrived, and compare with an older instance if one is still running.",
        "Something in the new code or its packaging that the previous version did not have: a "
        "mistake in a code path that is now exercised, a change to an interface that other parts "
        "did not expect, a missing data migration, or a library that behaves differently.",
        "Go back to the previous release straight away by redeploying the last version known to be "
        "good. Do not spend time debugging on the live service first. Pause any further releases "
        "to this service until the cause is understood and a fix has been reviewed and tested.",
        "After going back, failures should fade within a few minutes and the error that was filling "
        "the logs should stop appearing. Watch for ten more minutes to make sure it stays quiet "
        "before telling anyone the incident is over.",
        "Call the owning team's on-call engineer if going back does not restore service within "
        "fifteen minutes, or if the previous release turns out to be broken as well. Tell incident "
        "command if more than one service is affected.",
        "If nothing was released but a setting was changed shortly before the trouble began, use "
        "the misconfiguration runbook instead. If the service is being killed for memory, use the "
        "memory leak runbook.",
    ]),
    # --- 2: similar to 3, 10, 12 -----------------------------------------------------------
    (2, "Database connection pool exhaustion", [
        "Requests to the database are waiting. The service has used up its whole allowance of "
        "database connections, so new work queues for a free connection and eventually times out "
        "before it ever reaches the database.",
        "Latency climbs and errors follow as requests wait on the database and time out. Logs "
        "mention database timeouts and requests waiting. The service's CPU stays normal because it "
        "is idle while it waits, which can make the service look healthy from the outside.",
        "Check how much of the connection pool is in use: it sits at or very near its maximum. Look "
        "for log lines saying a connection is not available or that the pool is exhausted, with "
        "many requests waiting. Then look at individual queries: if they are quick and the delay is "
        "the wait for a connection, this is pool exhaustion.",
        "Connections held for too long or never given back, more concurrent work than the pool was "
        "sized for, a pool maximum set too low after a change, or a stall in the database that "
        "stops connections being returned promptly.",
        "Restart the affected instances to release held connections as a first step. Then raise the "
        "pool maximum, staying inside the database's own connection limit, and shed non-essential "
        "traffic. If connections are leaking, find the code path that does not return them.",
        "Pool usage should fall well below its maximum, the number of waiting requests should drop "
        "to zero and latency should return to normal within a few minutes. Watch it for half an "
        "hour in case the pool fills again.",
        "Call the database team if the database itself is close to its connection limit or is "
        "refusing new connections, since raising pool sizes elsewhere will then make things worse.",
        "If one query is simply taking seconds, use the slow query runbook. If pool use rises "
        "slowly over days, use the connection leak audit. If a cache failed first, use the cache "
        "runbook.",
    ]),
    # --- 3: similar to 2, 10, 12 -----------------------------------------------------------
    (3, "Slow query or missing index", [
        "Requests to the database are slow. A query that used to be fast now takes seconds, usually "
        "because an index is missing or is no longer being used, and every request that depends on "
        "that query waits for it.",
        "Latency climbs and errors follow as requests wait on the database and time out. Logs "
        "mention database timeouts and slow queries. The connection pool may fill as a side effect, "
        "because every connection is busy running the slow statement for longer than usual.",
        "Search the logs for slow query warnings and for query plans showing a full scan of a large "
        "table. Check whether a schema migration recently dropped or changed an index. The slowness "
        "is present at normal traffic, and a single query taking several seconds is the "
        "signature, rather than short queries waiting for a connection.",
        "An index that was dropped or never created, out-of-date table statistics, a code change "
        "that no longer uses the index, or a table that has grown past what the old plan can "
        "handle. Recent migrations are the first place to look.",
        "Recreate the missing index using a concurrent build so writes are not blocked, then refresh "
        "the table statistics. As a stopgap, cancel the long-running queries and add a statement "
        "timeout. Revert the migration that removed the index if one is found.",
        "The slow query should disappear from the logs, its run time should return to milliseconds "
        "and request latency should recover. Check the connection pool afterwards to confirm it has "
        "drained back to normal.",
        "Talk to the database team before building an index on a very large table during peak "
        "hours, since the build itself adds load and can take a long time to finish.",
        "If queries are quick but requests wait for connections, use the pool exhaustion runbook. "
        "If the database is overloaded because the cache failed, use the cache runbook.",
    ]),
    # --- 4: loose language ---------------------------------------------------------------
    (4, "Downstream dependency timeout", [
        "A service is failing because something it relies on is slow or not answering. Calls to it "
        "run out of time, retries pile on extra load, and the failure spreads upstream to the "
        "callers of this service.",
        "The service looks unhealthy yet its own resources are fine. Responses are slow, then "
        "failures follow, and the delay seems to cluster right around the point where it waits for "
        "something it talks to. Protective cut-offs may start rejecting calls.",
        "Work out which neighbour the slow calls are going to, using the messages about calls that "
        "gave up. Then check how that neighbour is doing. If it is struggling while this service's "
        "own processor and memory look ordinary, the problem lives over there, not here.",
        "The neighbour is overloaded, has been broken by its own release, is stuck waiting on its "
        "own database, or the network path between the two services has degraded and is dropping "
        "or delaying traffic.",
        "Do not restart the caller, since that does not help and loses state. Get the neighbour's "
        "team involved and fix it there. Meanwhile keep protective cut-offs engaged, cut back "
        "retries, and serve a reduced or cached response if the service supports it.",
        "The neighbour's response times should return to normal, the protective cut-off should close "
        "again by itself, and this service's failures should drop away within a few minutes of that "
        "happening.",
        "Page the neighbour's on-call engineer. If several different services are affected by the "
        "same neighbour, tell incident command so the response can be coordinated.",
        "If the failures are connection errors and not slow replies, use the DNS runbook. If the "
        "neighbour is slow because of a database problem, use the database runbooks.",
    ]),
    # --- 5: loose language ---------------------------------------------------------------
    (5, "Memory leak and OOM kills", [
        "A process uses more and more memory over time until it hits its limit and is killed by the "
        "platform. It then starts again, grows again and dies again, so the service keeps "
        "cycling between working and failing.",
        "The service keeps being restarted by the platform, and it behaves worse each time it comes "
        "up before it dies again. Failures arrive in bursts around the restarts and then ease off "
        "briefly while the fresh instance is healthy.",
        "Look at how memory use moves between restarts. If it climbs steadily after every start and "
        "the platform reports that it ended the process for using too much, a leak is the likely "
        "cause. Compare against restarts with a different explanation, such as a rollout.",
        "Something that is stored and never released, such as an ever-growing list or cache, a "
        "resource that is not closed, a memory limit set too low for the real workload, or a recent "
        "change that increased how much each request needs.",
        "Restart cycling hides the problem for a while, so scale out so each instance carries less "
        "load, and raise the memory limit as a stopgap. Capture a memory dump from an instance "
        "close to its limit before it is killed. Roll back if a release introduced the leak.",
        "Memory should stay flat and well below the limit for longer than the old time between "
        "kills, and restarts should stop altogether. Keep watching for at least two of the old "
        "cycles to be sure.",
        "Pass the memory dump and a graph of memory over time to the owning team. Escalate to "
        "incident command if the service cannot stay up even after scaling out.",
        "For questions about how big the heap should be on a service that is not being killed, use "
        "the heap tuning runbook. If memory trouble began with a rollout, use the bad deployment "
        "runbook.",
    ]),
    # --- 6: loose language ---------------------------------------------------------------
    (6, "Disk full", [
        "A storage volume used for logs, temporary files or database data has filled up. Anything "
        "that needs to save data fails at once, while reads often carry on working for a while "
        "longer, which makes the failure look odd.",
        "Saving things starts failing out of the blue, usually after a long, quiet creep upward that "
        "nobody noticed. Errors begin abruptly once the space runs out, and a warning about the "
        "volume being nearly full often exists from hours earlier.",
        "Check how full the storage volumes are and how fast they have been filling. If one is at or "
        "near the top, that is your answer, and the application messages will complain about being "
        "unable to save or write things. Find what grew by listing the largest folders.",
        "Log files with no rotation, a runaway temporary folder, a backup or export that was never "
        "cleaned up, or database write-ahead files piling up because shipping them elsewhere has "
        "been failing for a while.",
        "Free space immediately by deleting old rotated logs and stale temporary files, and start "
        "log rotation. Then extend the volume. Do not delete database data files by hand. Once "
        "stable, trace what grew and put a cleanup or a limit on it.",
        "Disk use should drop comfortably below the alert threshold, saving should work again and "
        "failures should stop. Check that whatever filled the disk is not still growing before "
        "closing the incident.",
        "Call the platform team if the volume cannot be extended or the database refuses to restart "
        "cleanly after space is freed. Tell the data owner before removing anything that is not "
        "plainly a log or temporary file.",
        "If the data came from a scheduled export that overran, use the batch job runbook. For "
        "problems with archived database logs, involve the database team as well.",
    ]),
    # --- 7: precise signals ----------------------------------------------------------------
    (7, "Expired TLS certificate", [
        "A service certificate passed its expiry date, so clients can no longer complete secure "
        "handshakes with it. Nothing about the application itself is wrong, which makes this easy "
        "to miss when looking only at the code and its recent changes.",
        "A sudden, near-total failure of connections to the service. The error rate steps up at the "
        "exact moment of expiry. Latency falls instead of rising because connections fail fast, "
        "and the request volume the service sees drops as clients give up.",
        "Search the logs for 'certificate has expired', 'x509' and 'SSL handshake failed' with a "
        "notAfter date in the past. Latency falls and request rate drops, the opposite of an "
        "overload. Check the certificate renewal job's logs for earlier failures or warnings.",
        "An automated renewal job that has been failing quietly, a certificate that was never "
        "enrolled in automation, or a DNS or challenge problem that blocked renewal and was never "
        "noticed because nothing alerted on it.",
        "Issue and install a renewed certificate, then reload or restart the service so it picks the "
        "new one up. If automated renewal failed, fix whatever blocked it and run the renewal by "
        "hand. Check other certificates issued around the same day for the same fault.",
        "Handshakes should succeed again, request volume should return to normal and the error rate "
        "should fall to its usual level. Confirm the new certificate's expiry date is far in the "
        "future.",
        "Call the security team if the issuing authority cannot be reached or there is any sign that "
        "private keys were exposed. Tell the service owner so renewal automation can be fixed.",
        "For rotating keys and other credentials, use the secrets rotation runbook. If clients "
        "fail for a reason other than the certificate, use the downstream dependency runbook.",
    ]),
    # --- 8: loose language ---------------------------------------------------------------
    (8, "Misconfiguration: environment variable or feature flag", [
        "A setting or feature switch was changed to a wrong value and the service fails when it "
        "loads it. Because nothing was released, people lose time looking at code that has not "
        "changed instead of at the settings that did.",
        "Trouble starts right after someone changed a setting, with no release in sight. The service "
        "complains about a value it does not like, or cannot reach something it should be able to "
        "reach, and it may restart to pick up the new value.",
        "Ask who changed settings recently and when. Compare the service's current settings with the "
        "last known good ones; a changed value that lines up with the start of the trouble is the "
        "likely cause. Rule out a release first by checking that nothing was rolled out in the "
        "same period.",
        "A wrong address, such as one pointing at a test system, a limit set to zero or a negative "
        "number, a feature switched on for everyone too early, or a simple typo in a setting's "
        "name that makes the default silently apply.",
        "Put the setting back to its previous value in the configuration service and reload the "
        "affected service. If a feature switch is the cause, turn it off. Afterwards add "
        "validation for that setting so a bad value is rejected before it can take effect.",
        "The service should start with valid settings, the complaints should stop and the audit "
        "history of the configuration service should show the reverted value. Watch for several "
        "minutes in case other instances still hold the old value.",
        "Call the team that owns the configuration service if reverting the value does not take "
        "effect. Tell the person who made the change, without blame, so they can help check "
        "related settings.",
        "If a release, not a setting change, came before the trouble, use the bad deployment "
        "runbook. If the setting concerns certificates or credentials, use the matching runbooks.",
    ]),
    # --- 9: loose language ---------------------------------------------------------------
    (9, "Traffic spike and rate limiting", [
        "Far more requests are arriving than the service was built to handle. It protects itself by "
        "turning some requests away, and capacity cannot grow fast enough to keep up with the "
        "demand, so everyone sees slowness or refusals.",
        "Far more people are knocking on the door than usual. The service gets sluggish, starts "
        "turning requests away with messages saying to slow down, and cannot add capacity any "
        "further even though automatic scaling is trying to.",
        "Compare the incoming volume with a normal day at this time. If it is several times higher "
        "and the machines are busy, this is demand and not a fault. Check whether the automatic "
        "scaling has already used up its allowance, and whether one caller accounts for most of "
        "the load.",
        "A sale or marketing push, a client stuck in a retry loop, a bot or crawler, or traffic "
        "that was redirected from another region after a problem there. Check whether the business "
        "told anyone about a planned event.",
        "Tighten limits on the heaviest caller, raise the ceiling on automatic scaling, and turn "
        "away non-essential traffic first. Block abusive sources at the edge. If a client is "
        "retrying aggressively, contact whoever owns that client and ask them to back off.",
        "Incoming volume should return towards normal or be absorbed by the added capacity, busy "
        "machines should cool down and the refusals should stop. Keep limits in place until demand "
        "has been normal for a while.",
        "Call the platform team to raise capacity limits quickly. Tell the business owner about any "
        "planned event that nobody mentioned, so capacity can be planned ahead next time.",
        "If load is uneven across servers while total traffic is normal, use the load balancer "
        "runbook. If the extra load is mostly retries after a failure elsewhere, start from the "
        "downstream dependency runbook.",
    ]),
    # --- 10: similar to 2, 3 ---------------------------------------------------------------
    (10, "Cache outage and cache stampede", [
        "The cache in front of a service became unavailable or was emptied, so every request now "
        "goes to the database instead. The database can saturate under the extra load and start "
        "making requests wait.",
        "Requests wait on the database and time out, with latency climbing and errors following. "
        "Logs mention database fallbacks and timeouts. The cache servers may refuse connections, "
        "and a sudden burst of identical lookups can appear for the same few keys.",
        "Check the cache hit ratio: it falls from around ninety percent to near zero first, and the "
        "database connection usage rises after it. Search the logs for refused connections to the "
        "cache, fallbacks to the database and bursts of concurrent loads for one key. The cache "
        "drop coming first separates this from a database problem.",
        "A cache node that crashed or restarted, an eviction storm, many keys expiring at the same "
        "moment, or a release that changed how keys are named so the old entries are never found.",
        "Restore the cache first by restarting or failing over the node. Then protect the database "
        "by turning on request coalescing or limiting how many cache misses may load at once, and "
        "warm the hottest keys gradually. Do not restart the application while the cache is down.",
        "The cache hit ratio should recover above eighty-five percent, database connection use "
        "should fall away and latency should return to normal. Watch the database closely while "
        "the cache refills, since a second stampede is possible.",
        "Call the cache platform team if the cluster cannot be restored within fifteen minutes, or "
        "if data in the cache cannot be rebuilt from the source of truth quickly enough.",
        "If the database is slow while the cache is healthy, use the slow query or connection pool "
        "runbooks. The cache runbook covers what to do first; those cover the database side.",
    ]),
    # --- 11: near miss to 5 -----------------------------------------------------------------
    (11, "JVM heap tuning and GC pressure", [
        "Guidance for sizing the JVM heap and tuning garbage collection on a service that is stable "
        "but spends too much time collecting garbage. It is a performance exercise to schedule and "
        "test carefully, not an emergency procedure for services being killed.",
        "Longer garbage collection pauses and processor time spent by the collector while memory use "
        "stays flat. There are no restarts and no kills by the platform. Latency has small "
        "periodic spikes that line up with collection pauses.",
        "Read the collector logs for long pauses, and check that the heap stays well below the "
        "container's limit and never reaches it. If the container is being killed for memory, stop "
        "here and use the memory leak runbook instead, because tuning will not help.",
        "A heap sized too small or too large for the workload, a collector that is a poor fit for "
        "the latency goal, or large short-lived allocations created by a particular request type "
        "or batch job.",
        "Change heap size flags and, if needed, the collector in a canary instance first. Change one "
        "flag at a time and compare pause histograms before and after. Roll the change out "
        "gradually, and keep the old flags ready so you can put them back at once.",
        "Pause times should fall below the target, the share of processor time spent in collection "
        "should decline, and the spikes in latency should flatten out across a full business day.",
        "Ask the performance engineering group before changing flags across the whole fleet. They "
        "keep a record of settings that worked for similar services.",
        "If the process is being killed for memory use or climbs steadily between restarts, use the "
        "memory leak and OOM kills runbook.",
    ]),
    # --- 12: near miss to 2 -----------------------------------------------------------------
    (12, "Database connection leak audit", [
        "A planned procedure for finding application code that fails to give database connections "
        "back to the pool, so that requests end up waiting. Use it for slow, recurring pool "
        "growth over days, not for an acute outage in progress.",
        "Connection pool usage creeps upward over days and only falls after a restart. Requests "
        "occasionally wait on the database and time out near the end of each cycle, but there is "
        "no sudden event and no clear start time to point at.",
        "Switch on the pool's leak detection with a threshold of sixty seconds and read the stack "
        "traces it logs for connections held too long. Compare pool usage across several weeks "
        "to see the slow upward drift and the drops at each restart.",
        "Code paths that open a connection and do not close it when an error occurs, transactions "
        "that stay open far too long, cursors that are forgotten, or background tasks that "
        "hold a connection while waiting on something slow.",
        "Fix the code path that leaks and make sure connections are always closed, for example with "
        "automatic resource handling. This is a development task, not an incident response. If "
        "there is an active outage, restart instances and use the pool exhaustion runbook.",
        "Pool usage should stay flat over several days with no restarts needed, and the leak "
        "detector should stop reporting connections held beyond the threshold in the logs.",
        "Raise a ticket with the owning team and attach the stack traces. No paging is needed, since "
        "this is slow-moving, unless the pool is already close to full right now.",
        "For an acute outage with all connections in use, use the connection pool exhaustion "
        "runbook. For one very slow query, use the slow query runbook.",
    ]),
    # --- 13-18: unrelated ---------------------------------------------------------------
    (13, "DNS resolution failures", [
        "Services cannot translate hostnames into addresses, so calls fail before a connection is "
        "even attempted. The problem often affects many services at the same moment, which is the "
        "main clue that it is not a single service's fault.",
        "Errors that say a host cannot be found or that name resolution failed temporarily. They "
        "appear across several unrelated services at once, and calls to addresses written as "
        "numbers still work normally.",
        "Run a name lookup from inside an affected instance and compare it with a lookup from a "
        "healthy one. Check the cluster DNS servers, their logs and their resource usage, and "
        "test whether the upstream resolver answers quickly.",
        "An overloaded or crashed cluster DNS service, an unreachable upstream resolver, or a recent "
        "network policy change that blocks the lookups from certain places.",
        "Restart the cluster DNS pods and scale them out, then check that the upstream resolver is "
        "reachable. Revert any network policy change made shortly before the failures began, and "
        "lengthen lookup caching on clients if the resolver is flaky.",
        "Lookups from affected instances should succeed quickly and the connection errors in the "
        "logs should stop. Confirm the same from at least two other services before closing.",
        "Call the network team if the upstream resolver cannot be reached from the cluster at all or "
        "if the problem spans more than one cluster or region.",
        "If connections work but replies are slow, use the downstream dependency timeout runbook.",
    ]),
    (14, "Kafka consumer lag", [
        "A consumer group is falling behind the producers writing to a topic, so event processing is "
        "delayed. Services that answer requests directly are usually unaffected, and the damage "
        "shows up in data that is stale or notifications that arrive late.",
        "Consumer lag grows steadily on one or more partitions, and downstream data is out of date. "
        "Dashboards that depend on the events show old numbers while request-serving services "
        "keep working normally.",
        "Look at the lag of the consumer group on each partition and the health of every consumer "
        "instance. Check whether one partition is stuck while others progress, which points at a "
        "single bad message, and whether consumers are repeatedly rebalancing.",
        "A slow processing step in the consumer, too few consumer instances for the partition count, "
        "a poison message that fails every time it is read, or a rebalance loop caused by slow "
        "heartbeats.",
        "Scale the consumers out up to the number of partitions, move a poison message to a "
        "dead-letter topic so processing can continue, and fix whatever step is slow. Avoid "
        "restarting all consumers at once because that triggers a rebalance.",
        "Lag should fall steadily towards zero on every partition and the downstream data should "
        "catch up. Watch the rate of catching up to estimate when the backlog will be gone.",
        "Call the data platform team if the brokers are unhealthy or if lag grows on many consumer "
        "groups at the same time.",
        "For queues that are not Kafka topics, use the queue backlog drain runbook.",
    ]),
    (15, "Queue backlog drain", [
        "A work queue has built up a large backlog and needs to be emptied safely without "
        "overwhelming the systems that the workers depend on. Draining too fast can cause a "
        "second incident, so the aim is a controlled catch-up.",
        "The number of waiting jobs and the age of the oldest job keep rising. Work completes late "
        "or not at all, and customers may report that emails, exports or reports are delayed.",
        "Check the queue depth and oldest job age over the last hour, and how many jobs the workers "
        "finish per minute. Compare that with the arrival rate to see whether the backlog is "
        "still growing or has started to shrink.",
        "Too few workers, a stuck or crashed worker pool, one very slow job type blocking others, or "
        "a burst of enqueued work caused by a release or an upstream retry loop.",
        "Add workers gradually while watching the databases and services they call, and pause "
        "low-priority producers until the backlog clears. Move poison jobs aside. Do not raise "
        "worker counts sharply, as that can overwhelm shared systems.",
        "The number of waiting jobs should return to its normal range and the oldest job age should "
        "drop below the agreed limit. Confirm that new jobs are being finished promptly.",
        "Call the owning team if a downstream system is throttling the workers or if jobs cannot be "
        "retried safely without side effects.",
        "For event streams with consumer groups, use the Kafka consumer lag runbook.",
    ]),
    (16, "Load balancer unhealthy targets", [
        "The load balancer has marked some of its backend servers as unhealthy and stopped sending "
        "them traffic. The remaining servers carry more load, and if too many are removed, the "
        "service becomes slow or starts refusing requests.",
        "Fewer healthy servers than expected behind the balancer, uneven load on the remaining ones, "
        "and intermittent gateway errors for a share of requests. Some servers look fine when "
        "checked directly.",
        "Look at the balancer's view of each server and the recent answers of the health check "
        "endpoint, including how long it takes to reply. Compare a server marked unhealthy with "
        "one marked healthy to see what differs.",
        "A health check endpoint that is failing or slow, a threshold that is too strict, a network "
        "or security rule change that blocks the checks, or servers that are really overloaded.",
        "Fix the health check endpoint, or relax the thresholds temporarily, and put healthy "
        "servers back into rotation. Revert any recent firewall or security rule changes. Add "
        "capacity if the servers are genuinely overloaded.",
        "All servers should report healthy and gateway errors should stop. Confirm that traffic is "
        "spread roughly evenly across servers again.",
        "Call the network team if the balancer itself seems faulty or if checks fail from the "
        "balancer but pass from everywhere else.",
        "If every server is healthy but overloaded by demand, use the traffic spike runbook.",
    ]),
    (17, "Scheduled batch job missed", [
        "A scheduled batch job did not run, or did not finish, leaving reports, exports or "
        "derived data stale. Nothing in the request path is affected, which is why it is often "
        "noticed only when someone asks why a report is empty.",
        "Reports and data files are missing or out of date. People say the morning figures look "
        "old. There are no errors in the services that answer customer requests during this "
        "period.",
        "Check the scheduler's history for the job's last run time and exit status, and read the "
        "output of the last attempt. Compare how long the job normally runs with how long it ran "
        "this time.",
        "A scheduler outage, a job that exceeded its time limit as the data grew, an expired "
        "credential used by the job, or an upstream data source that was late or empty.",
        "Run the job again by hand, extend its time limit if the data volume justifies it, and fix "
        "the underlying failure. Tell the people who depend on the output that it will arrive "
        "late, and the expected time.",
        "The job should complete with a success status and the downstream reports should update "
        "with current numbers. Check the output files are of a plausible size.",
        "Call the data engineering team if the job is blocked on missing upstream data or if a "
        "rerun would overwrite results that other teams have already used.",
        "If the job failed to sign in, use the secrets rotation runbook.",
    ]),
    (18, "Secrets rotation", [
        "The procedure for replacing credentials, API keys and signing keys on a regular schedule or "
        "after a suspected exposure. A rotation done carelessly can itself cause an outage when "
        "some consumer keeps using the old secret.",
        "Sign-in failures that start at the time of a rotation, or a security alert saying that a "
        "credential may have been exposed in a log, a repository or a message. Some "
        "environments fail while others work.",
        "Check which credentials were rotated recently and which services still use the old value. "
        "Compare the time of the first sign-in failure with the rotation time recorded in the "
        "secrets manager's audit history.",
        "A consumer still holding the old secret, a rotation applied to only some environments, or a "
        "secret cached for longer than the overlap period that was planned.",
        "Update the consumers with the new secret and, only after no client uses the old one, revoke "
        "it. If exposure is suspected, rotate immediately and accept brief disruption. Keep both "
        "values valid for a short overlap whenever the system allows it.",
        "Sign-ins should succeed across all consumers and the old secret should be confirmed as "
        "revoked. Check the audit history shows no further use of the old value.",
        "Call the security team for any suspected exposure, and before revoking a secret that is "
        "shared by many services.",
        "For TLS certificates specifically, use the expired TLS certificate runbook.",
    ]),
]


# Sentences appended to short sections (escalation, cross-references and a few others) so that
# every section reaches 30 words and stands alone as a chunk.
_EXTRA: dict[tuple[int, int], str] = {
    (2, 7): "Share the pool graphs so they can see which services hold the most connections.",
    (3, 8): "If pool use rises slowly over days instead, use the connection leak audit.",
    (4, 7): "Share which calls are timing out and since when, so they can find the cause faster.",
    (4, 8): "If the neighbour is simply overloaded by demand, use the traffic spike runbook.",
    (5, 7): "Include the dates of recent releases, since they help rule a rollout in or out.",
    (6, 8): "The database team can tell you which files are safe to remove.",
    (7, 8): "If the failures began right after a rollout, check the bad deployment runbook first.",
    (8, 8): "If requests are refused because of volume alone, use the traffic spike runbook.",
    (9, 7): "Ask them whether any other region has spare room to take some of the load.",
    (11, 7): "They can also review your before-and-after pause measurements for any change you propose.",
    (11, 8): "Tuning flags will not fix a leak, and can hide the symptom for a day or two.",
    (12, 6): "Compare the new weekly graph with the one from before the fix to be sure.",
    (12, 8): "This audit is only for slow drift, so do not start it during an incident.",
    (13, 4): "Also check for a misconfigured search domain that makes each lookup try several wrong "
             "names first.",
    (13, 6): "Also check the DNS servers' own query latency is back at its usual level.",
    (13, 7): "Include the failing hostnames and the time of the first failure in your message.",
    (13, 8): "If requests are turned away because healthy servers are overloaded, use the traffic "
             "spike runbook instead of this one.",
    (14, 7): "That pattern points at the cluster and not at one consumer. Include topic names and "
             "lag graphs.",
    (14, 8): "For a job that never ran at all, use the scheduled batch job runbook, because the "
             "checks and the people to call are different.",
    (15, 7): "Ask them which job types are safe to repeat before you restart anything that has "
             "already run partway.",
    (15, 8): "If the backlog exists because a database or another service is slow, fix that first, "
             "or extra workers will only make it worse.",
    (16, 6): "Also check that the health check endpoint answers quickly under normal load for ten "
             "minutes.",
    (16, 7): "Tell them which servers were removed and when, so they can match it against their "
             "own logs.",
    (16, 8): "If servers are healthy but the service they call is slow, use the downstream "
             "dependency runbook, because the balancer is not the cause there.",
    (17, 6): "Ask one person who uses the report to confirm the figures look right.",
    (17, 7): "Agree with them whether to rerun in full or only for the missing period.",
    (17, 8): "If the job filled a disk while running, use the disk full runbook, and if it ran but "
             "fell behind other work, use the queue backlog runbook.",
    (18, 4): "A deployment pipeline that restores the previous value from an old configuration "
             "file is another common cause.",
    (18, 6): "Also check that no scheduled job still holds a copy of the old value in its settings.",
    (18, 7): "Tell them where the value appeared, how long it was visible and who could have read "
             "it during that time.",
    (18, 8): "If a service fails only after a setting was changed, use the misconfiguration "
             "runbook, since a wrong credential setting looks like a failed rotation but is fixed "
             "differently.",
}
RUNBOOKS = [
    (n, t, [b + (" " + _EXTRA[(n, i)] if (n, i) in _EXTRA else "") for i, b in enumerate(bodies, 1)])
    for n, t, bodies in RUNBOOKS
]


def slug(title: str) -> str:
    keep = "".join(c.lower() if c.isalnum() else "-" for c in title)
    return "-".join(part for part in keep.split("-") if part)[:48]


def render(number: int, title: str, bodies: list[str]) -> str:
    lines = [f"# Runbook {number:02d}: {title}", ""]
    for i, (heading, body) in enumerate(zip(SECTIONS, bodies, strict=True), start=1):
        lines += [f"## {i}. {heading}", "", body, ""]
    return "\n".join(lines)
