# Runbook 07: Expired TLS certificate

## 1. Summary

A service certificate passed its expiry date, so clients can no longer complete secure handshakes with it. Nothing about the application itself is wrong, which makes this easy to miss when looking only at the code and its recent changes.

## 2. Symptoms

A sudden, near-total failure of connections to the service. The error rate steps up at the exact moment of expiry. Latency falls instead of rising because connections fail fast, and the request volume the service sees drops as clients give up.

## 3. How to confirm

Search the logs for 'certificate has expired', 'x509' and 'SSL handshake failed' with a notAfter date in the past. Latency falls and request rate drops, the opposite of an overload. Check the certificate renewal job's logs for earlier failures or warnings.

## 4. Likely causes

An automated renewal job that has been failing quietly, a certificate that was never enrolled in automation, or a DNS or challenge problem that blocked renewal and was never noticed because nothing alerted on it.

## 5. Mitigation

Issue and install a renewed certificate, then reload or restart the service so it picks the new one up. If automated renewal failed, fix whatever blocked it and run the renewal by hand. Check other certificates issued around the same day for the same fault.

## 6. Verify recovery

Handshakes should succeed again, request volume should return to normal and the error rate should fall to its usual level. Confirm the new certificate's expiry date is far in the future.

## 7. Escalation

Call the security team if the issuing authority cannot be reached or there is any sign that private keys were exposed. Tell the service owner so renewal automation can be fixed.

## 8. Related runbooks

For rotating keys and other credentials, use the secrets rotation runbook. If clients fail for a reason other than the certificate, use the downstream dependency runbook. If the failures began right after a rollout, check the bad deployment runbook first.
