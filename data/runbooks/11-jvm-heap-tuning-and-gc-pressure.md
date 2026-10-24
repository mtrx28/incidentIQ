# Runbook 11: JVM heap tuning and GC pressure

## 1. Summary

Guidance for sizing the JVM heap and tuning garbage collection on a service that is stable but spends too much time collecting garbage. It is a performance exercise to schedule and test carefully, not an emergency procedure for services being killed.

## 2. Symptoms

Longer garbage collection pauses and processor time spent by the collector while memory use stays flat. There are no restarts and no kills by the platform. Latency has small periodic spikes that line up with collection pauses.

## 3. How to confirm

Read the collector logs for long pauses, and check that the heap stays well below the container's limit and never reaches it. If the container is being killed for memory, stop here and use the memory leak runbook instead, because tuning will not help.

## 4. Likely causes

A heap sized too small or too large for the workload, a collector that is a poor fit for the latency goal, or large short-lived allocations created by a particular request type or batch job.

## 5. Mitigation

Change heap size flags and, if needed, the collector in a canary instance first. Change one flag at a time and compare pause histograms before and after. Roll the change out gradually, and keep the old flags ready so you can put them back at once.

## 6. Verify recovery

Pause times should fall below the target, the share of processor time spent in collection should decline, and the spikes in latency should flatten out across a full business day.

## 7. Escalation

Ask the performance engineering group before changing flags across the whole fleet. They keep a record of settings that worked for similar services. They can also review your before-and-after pause measurements for any change you propose.

## 8. Related runbooks

If the process is being killed for memory use or climbs steadily between restarts, use the memory leak and OOM kills runbook. Tuning flags will not fix a leak, and can hide the symptom for a day or two.
