# Runbook 05: Memory leak and OOM kills

## 1. Summary

A process uses more and more memory over time until it hits its limit and is killed by the platform. It then starts again, grows again and dies again, so the service keeps cycling between working and failing.

## 2. Symptoms

The service keeps being restarted by the platform, and it behaves worse each time it comes up before it dies again. Failures arrive in bursts around the restarts and then ease off briefly while the fresh instance is healthy.

## 3. How to confirm

Look at how memory use moves between restarts. If it climbs steadily after every start and the platform reports that it ended the process for using too much, a leak is the likely cause. Compare against restarts with a different explanation, such as a rollout.

## 4. Likely causes

Something that is stored and never released, such as an ever-growing list or cache, a resource that is not closed, a memory limit set too low for the real workload, or a recent change that increased how much each request needs.

## 5. Mitigation

Restart cycling hides the problem for a while, so scale out so each instance carries less load, and raise the memory limit as a stopgap. Capture a memory dump from an instance close to its limit before it is killed. Roll back if a release introduced the leak.

## 6. Verify recovery

Memory should stay flat and well below the limit for longer than the old time between kills, and restarts should stop altogether. Keep watching for at least two of the old cycles to be sure.

## 7. Escalation

Pass the memory dump and a graph of memory over time to the owning team. Escalate to incident command if the service cannot stay up even after scaling out. Include the dates of recent releases, since they help rule a rollout in or out.

## 8. Related runbooks

For questions about how big the heap should be on a service that is not being killed, use the heap tuning runbook. If memory trouble began with a rollout, use the bad deployment runbook.
