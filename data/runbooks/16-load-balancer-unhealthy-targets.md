# Runbook 16: Load balancer unhealthy targets

## 1. Summary

The load balancer has marked some of its backend servers as unhealthy and stopped sending them traffic. The remaining servers carry more load, and if too many are removed, the service becomes slow or starts refusing requests.

## 2. Symptoms

Fewer healthy servers than expected behind the balancer, uneven load on the remaining ones, and intermittent gateway errors for a share of requests. Some servers look fine when checked directly.

## 3. How to confirm

Look at the balancer's view of each server and the recent answers of the health check endpoint, including how long it takes to reply. Compare a server marked unhealthy with one marked healthy to see what differs.

## 4. Likely causes

A health check endpoint that is failing or slow, a threshold that is too strict, a network or security rule change that blocks the checks, or servers that are really overloaded.

## 5. Mitigation

Fix the health check endpoint, or relax the thresholds temporarily, and put healthy servers back into rotation. Revert any recent firewall or security rule changes. Add capacity if the servers are genuinely overloaded.

## 6. Verify recovery

All servers should report healthy and gateway errors should stop. Confirm that traffic is spread roughly evenly across servers again. Also check that the health check endpoint answers quickly under normal load for ten minutes.

## 7. Escalation

Call the network team if the balancer itself seems faulty or if checks fail from the balancer but pass from everywhere else. Tell them which servers were removed and when, so they can match it against their own logs.

## 8. Related runbooks

If every server is healthy but overloaded by demand, use the traffic spike runbook. If servers are healthy but the service they call is slow, use the downstream dependency runbook, because the balancer is not the cause there.
