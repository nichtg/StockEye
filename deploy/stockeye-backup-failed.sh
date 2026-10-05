#!/bin/sh
# Run by stockeye-backup-failed.service (the backup service's OnFailure=). Makes a failed backup
# loud: a crit-level syslog line and a marker file that `ls /var/lib/stockeye` shows at a glance.
install -d -m 0700 /var/lib/stockeye
date -u +"backup failed at %Y-%m-%dT%H:%M:%SZ" >/var/lib/stockeye/BACKUP_FAILED
logger -p user.crit -t stockeye-backup "BACKUP FAILED: see journalctl -u stockeye-backup"
