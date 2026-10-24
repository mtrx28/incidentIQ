# Runbook 14: Kafka consumer lag

## 1. Summary

A consumer group is falling behind the producers writing to a topic, so event processing is delayed. Services that answer requests directly are usually unaffected, and the damage shows up in data that is stale or notifications that arrive late.

## 2. Symptoms

Consumer lag grows steadily on one or more partitions, and downstream data is out of date. Dashboards that depend on the events show old numbers while request-serving services keep working normally.

## 3. How to confirm

Look at the lag of the consumer group on each partition and the health of every consumer instance. Check whether one partition is stuck while others progress, which points at a single bad message, and whether consumers are repeatedly rebalancing.

## 4. Likely causes

A slow processing step in the consumer, too few consumer instances for the partition count, a poison message that fails every time it is read, or a rebalance loop caused by slow heartbeats.

## 5. Mitigation

Scale the consumers out up to the number of partitions, move a poison message to a dead-letter topic so processing can continue, and fix whatever step is slow. Avoid restarting all consumers at once because that triggers a rebalance.

## 6. Verify recovery

Lag should fall steadily towards zero on every partition and the downstream data should catch up. Watch the rate of catching up to estimate when the backlog will be gone.

## 7. Escalation

Call the data platform team if the brokers are unhealthy or if lag grows on many consumer groups at the same time. That pattern points at the cluster and not at one consumer. Include topic names and lag graphs.

## 8. Related runbooks

For queues that are not Kafka topics, use the queue backlog drain runbook. For a job that never ran at all, use the scheduled batch job runbook, because the checks and the people to call are different.
