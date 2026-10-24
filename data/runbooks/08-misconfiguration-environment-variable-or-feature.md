# Runbook 08: Misconfiguration: environment variable or feature flag

## 1. Summary

A setting or feature switch was changed to a wrong value and the service fails when it loads it. Because nothing was released, people lose time looking at code that has not changed instead of at the settings that did.

## 2. Symptoms

Trouble starts right after someone changed a setting, with no release in sight. The service complains about a value it does not like, or cannot reach something it should be able to reach, and it may restart to pick up the new value.

## 3. How to confirm

Ask who changed settings recently and when. Compare the service's current settings with the last known good ones; a changed value that lines up with the start of the trouble is the likely cause. Rule out a release first by checking that nothing was rolled out in the same period.

## 4. Likely causes

A wrong address, such as one pointing at a test system, a limit set to zero or a negative number, a feature switched on for everyone too early, or a simple typo in a setting's name that makes the default silently apply.

## 5. Mitigation

Put the setting back to its previous value in the configuration service and reload the affected service. If a feature switch is the cause, turn it off. Afterwards add validation for that setting so a bad value is rejected before it can take effect.

## 6. Verify recovery

The service should start with valid settings, the complaints should stop and the audit history of the configuration service should show the reverted value. Watch for several minutes in case other instances still hold the old value.

## 7. Escalation

Call the team that owns the configuration service if reverting the value does not take effect. Tell the person who made the change, without blame, so they can help check related settings.

## 8. Related runbooks

If a release, not a setting change, came before the trouble, use the bad deployment runbook. If the setting concerns certificates or credentials, use the matching runbooks. If requests are refused because of volume alone, use the traffic spike runbook.
