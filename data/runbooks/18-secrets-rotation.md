# Runbook 18: Secrets rotation

## 1. Summary

The procedure for replacing credentials, API keys and signing keys on a regular schedule or after a suspected exposure. A rotation done carelessly can itself cause an outage when some consumer keeps using the old secret.

## 2. Symptoms

Sign-in failures that start at the time of a rotation, or a security alert saying that a credential may have been exposed in a log, a repository or a message. Some environments fail while others work.

## 3. How to confirm

Check which credentials were rotated recently and which services still use the old value. Compare the time of the first sign-in failure with the rotation time recorded in the secrets manager's audit history.

## 4. Likely causes

A consumer still holding the old secret, a rotation applied to only some environments, or a secret cached for longer than the overlap period that was planned. A deployment pipeline that restores the previous value from an old configuration file is another common cause.

## 5. Mitigation

Update the consumers with the new secret and, only after no client uses the old one, revoke it. If exposure is suspected, rotate immediately and accept brief disruption. Keep both values valid for a short overlap whenever the system allows it.

## 6. Verify recovery

Sign-ins should succeed across all consumers and the old secret should be confirmed as revoked. Check the audit history shows no further use of the old value. Also check that no scheduled job still holds a copy of the old value in its settings.

## 7. Escalation

Call the security team for any suspected exposure, and before revoking a secret that is shared by many services. Tell them where the value appeared, how long it was visible and who could have read it during that time.

## 8. Related runbooks

For TLS certificates specifically, use the expired TLS certificate runbook. If a service fails only after a setting was changed, use the misconfiguration runbook, since a wrong credential setting looks like a failed rotation but is fixed differently.
