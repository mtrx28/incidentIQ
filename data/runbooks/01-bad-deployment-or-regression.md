# Runbook 01: Bad deployment or regression

## 1. Summary

A new version of a service went out and something in it does not work. This is the most common reason for a sudden, lasting rise in failures, and it is usually fixed fastest by undoing the change rather than by investigating on the live system.

## 2. Symptoms

Things go wrong shortly after a rollout. Customers start seeing failures, dashboards turn red around the time the new version went out, and the problem does not fade by itself. The service may also restart a few times while the new version rolls through.

## 3. How to confirm

Line the start of the trouble up against the release timeline. If it began just after a rollout and the previous version was healthy, suspect the release. Look at what the service wrote to its logs while the new version was starting and when the first failures arrived, and compare with an older instance if one is still running.

## 4. Likely causes

Something in the new code or its packaging that the previous version did not have: a mistake in a code path that is now exercised, a change to an interface that other parts did not expect, a missing data migration, or a library that behaves differently.

## 5. Mitigation

Go back to the previous release straight away by redeploying the last version known to be good. Do not spend time debugging on the live service first. Pause any further releases to this service until the cause is understood and a fix has been reviewed and tested.

## 6. Verify recovery

After going back, failures should fade within a few minutes and the error that was filling the logs should stop appearing. Watch for ten more minutes to make sure it stays quiet before telling anyone the incident is over.

## 7. Escalation

Call the owning team's on-call engineer if going back does not restore service within fifteen minutes, or if the previous release turns out to be broken as well. Tell incident command if more than one service is affected.

## 8. Related runbooks

If nothing was released but a setting was changed shortly before the trouble began, use the misconfiguration runbook instead. If the service is being killed for memory, use the memory leak runbook.
