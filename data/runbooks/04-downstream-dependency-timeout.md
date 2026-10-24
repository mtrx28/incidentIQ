# Runbook 04: Downstream dependency timeout

## 1. Summary

A service is failing because something it relies on is slow or not answering. Calls to it run out of time, retries pile on extra load, and the failure spreads upstream to the callers of this service.

## 2. Symptoms

The service looks unhealthy yet its own resources are fine. Responses are slow, then failures follow, and the delay seems to cluster right around the point where it waits for something it talks to. Protective cut-offs may start rejecting calls.

## 3. How to confirm

Work out which neighbour the slow calls are going to, using the messages about calls that gave up. Then check how that neighbour is doing. If it is struggling while this service's own processor and memory look ordinary, the problem lives over there, not here.

## 4. Likely causes

The neighbour is overloaded, has been broken by its own release, is stuck waiting on its own database, or the network path between the two services has degraded and is dropping or delaying traffic.

## 5. Mitigation

Do not restart the caller, since that does not help and loses state. Get the neighbour's team involved and fix it there. Meanwhile keep protective cut-offs engaged, cut back retries, and serve a reduced or cached response if the service supports it.

## 6. Verify recovery

The neighbour's response times should return to normal, the protective cut-off should close again by itself, and this service's failures should drop away within a few minutes of that happening.

## 7. Escalation

Page the neighbour's on-call engineer. If several different services are affected by the same neighbour, tell incident command so the response can be coordinated. Share which calls are timing out and since when, so they can find the cause faster.

## 8. Related runbooks

If the failures are connection errors and not slow replies, use the DNS runbook. If the neighbour is slow because of a database problem, use the database runbooks. If the neighbour is simply overloaded by demand, use the traffic spike runbook.
