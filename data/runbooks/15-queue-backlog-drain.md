# Runbook 15: Queue backlog drain

## 1. Summary

A work queue has built up a large backlog and needs to be emptied safely without overwhelming the systems that the workers depend on. Draining too fast can cause a second incident, so the aim is a controlled catch-up.

## 2. Symptoms

The number of waiting jobs and the age of the oldest job keep rising. Work completes late or not at all, and customers may report that emails, exports or reports are delayed.

## 3. How to confirm

Check the queue depth and oldest job age over the last hour, and how many jobs the workers finish per minute. Compare that with the arrival rate to see whether the backlog is still growing or has started to shrink.

## 4. Likely causes

Too few workers, a stuck or crashed worker pool, one very slow job type blocking others, or a burst of enqueued work caused by a release or an upstream retry loop.

## 5. Mitigation

Add workers gradually while watching the databases and services they call, and pause low-priority producers until the backlog clears. Move poison jobs aside. Do not raise worker counts sharply, as that can overwhelm shared systems.

## 6. Verify recovery

The number of waiting jobs should return to its normal range and the oldest job age should drop below the agreed limit. Confirm that new jobs are being finished promptly.

## 7. Escalation

Call the owning team if a downstream system is throttling the workers or if jobs cannot be retried safely without side effects. Ask them which job types are safe to repeat before you restart anything that has already run partway.

## 8. Related runbooks

For event streams with consumer groups, use the Kafka consumer lag runbook. If the backlog exists because a database or another service is slow, fix that first, or extra workers will only make it worse.
