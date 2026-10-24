# Runbook 06: Disk full

## 1. Summary

A storage volume used for logs, temporary files or database data has filled up. Anything that needs to save data fails at once, while reads often carry on working for a while longer, which makes the failure look odd.

## 2. Symptoms

Saving things starts failing out of the blue, usually after a long, quiet creep upward that nobody noticed. Errors begin abruptly once the space runs out, and a warning about the volume being nearly full often exists from hours earlier.

## 3. How to confirm

Check how full the storage volumes are and how fast they have been filling. If one is at or near the top, that is your answer, and the application messages will complain about being unable to save or write things. Find what grew by listing the largest folders.

## 4. Likely causes

Log files with no rotation, a runaway temporary folder, a backup or export that was never cleaned up, or database write-ahead files piling up because shipping them elsewhere has been failing for a while.

## 5. Mitigation

Free space immediately by deleting old rotated logs and stale temporary files, and start log rotation. Then extend the volume. Do not delete database data files by hand. Once stable, trace what grew and put a cleanup or a limit on it.

## 6. Verify recovery

Disk use should drop comfortably below the alert threshold, saving should work again and failures should stop. Check that whatever filled the disk is not still growing before closing the incident.

## 7. Escalation

Call the platform team if the volume cannot be extended or the database refuses to restart cleanly after space is freed. Tell the data owner before removing anything that is not plainly a log or temporary file.

## 8. Related runbooks

If the data came from a scheduled export that overran, use the batch job runbook. For problems with archived database logs, involve the database team as well. The database team can tell you which files are safe to remove.
