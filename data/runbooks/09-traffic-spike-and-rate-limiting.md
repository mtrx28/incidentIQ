# Runbook 09: Traffic spike and rate limiting

## 1. Summary

Far more requests are arriving than the service was built to handle. It protects itself by turning some requests away, and capacity cannot grow fast enough to keep up with the demand, so everyone sees slowness or refusals.

## 2. Symptoms

Far more people are knocking on the door than usual. The service gets sluggish, starts turning requests away with messages saying to slow down, and cannot add capacity any further even though automatic scaling is trying to.

## 3. How to confirm

Compare the incoming volume with a normal day at this time. If it is several times higher and the machines are busy, this is demand and not a fault. Check whether the automatic scaling has already used up its allowance, and whether one caller accounts for most of the load.

## 4. Likely causes

A sale or marketing push, a client stuck in a retry loop, a bot or crawler, or traffic that was redirected from another region after a problem there. Check whether the business told anyone about a planned event.

## 5. Mitigation

Tighten limits on the heaviest caller, raise the ceiling on automatic scaling, and turn away non-essential traffic first. Block abusive sources at the edge. If a client is retrying aggressively, contact whoever owns that client and ask them to back off.

## 6. Verify recovery

Incoming volume should return towards normal or be absorbed by the added capacity, busy machines should cool down and the refusals should stop. Keep limits in place until demand has been normal for a while.

## 7. Escalation

Call the platform team to raise capacity limits quickly. Tell the business owner about any planned event that nobody mentioned, so capacity can be planned ahead next time. Ask them whether any other region has spare room to take some of the load.

## 8. Related runbooks

If load is uneven across servers while total traffic is normal, use the load balancer runbook. If the extra load is mostly retries after a failure elsewhere, start from the downstream dependency runbook.
