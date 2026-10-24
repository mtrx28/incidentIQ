# Runbook 17: Scheduled batch job missed

## 1. Summary

A scheduled batch job did not run, or did not finish, leaving reports, exports or derived data stale. Nothing in the request path is affected, which is why it is often noticed only when someone asks why a report is empty.

## 2. Symptoms

Reports and data files are missing or out of date. People say the morning figures look old. There are no errors in the services that answer customer requests during this period.

## 3. How to confirm

Check the scheduler's history for the job's last run time and exit status, and read the output of the last attempt. Compare how long the job normally runs with how long it ran this time.

## 4. Likely causes

A scheduler outage, a job that exceeded its time limit as the data grew, an expired credential used by the job, or an upstream data source that was late or empty.

## 5. Mitigation

Run the job again by hand, extend its time limit if the data volume justifies it, and fix the underlying failure. Tell the people who depend on the output that it will arrive late, and the expected time.

## 6. Verify recovery

The job should complete with a success status and the downstream reports should update with current numbers. Check the output files are of a plausible size. Ask one person who uses the report to confirm the figures look right.

## 7. Escalation

Call the data engineering team if the job is blocked on missing upstream data or if a rerun would overwrite results that other teams have already used. Agree with them whether to rerun in full or only for the missing period.

## 8. Related runbooks

If the job failed to sign in, use the secrets rotation runbook. If the job filled a disk while running, use the disk full runbook, and if it ran but fell behind other work, use the queue backlog runbook.
