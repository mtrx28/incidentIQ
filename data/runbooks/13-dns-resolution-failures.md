# Runbook 13: DNS resolution failures

## 1. Summary

Services cannot translate hostnames into addresses, so calls fail before a connection is even attempted. The problem often affects many services at the same moment, which is the main clue that it is not a single service's fault.

## 2. Symptoms

Errors that say a host cannot be found or that name resolution failed temporarily. They appear across several unrelated services at once, and calls to addresses written as numbers still work normally.

## 3. How to confirm

Run a name lookup from inside an affected instance and compare it with a lookup from a healthy one. Check the cluster DNS servers, their logs and their resource usage, and test whether the upstream resolver answers quickly.

## 4. Likely causes

An overloaded or crashed cluster DNS service, an unreachable upstream resolver, or a recent network policy change that blocks the lookups from certain places. Also check for a misconfigured search domain that makes each lookup try several wrong names first.

## 5. Mitigation

Restart the cluster DNS pods and scale them out, then check that the upstream resolver is reachable. Revert any network policy change made shortly before the failures began, and lengthen lookup caching on clients if the resolver is flaky.

## 6. Verify recovery

Lookups from affected instances should succeed quickly and the connection errors in the logs should stop. Confirm the same from at least two other services before closing. Also check the DNS servers' own query latency is back at its usual level.

## 7. Escalation

Call the network team if the upstream resolver cannot be reached from the cluster at all or if the problem spans more than one cluster or region. Include the failing hostnames and the time of the first failure in your message.

## 8. Related runbooks

If connections work but replies are slow, use the downstream dependency timeout runbook. If requests are turned away because healthy servers are overloaded, use the traffic spike runbook instead of this one.
