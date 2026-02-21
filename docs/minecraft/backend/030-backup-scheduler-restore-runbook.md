---
title: 030 Backup Scheduler + Restore Runbook
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - backup
  - restore
  - google-drive
---
# 030 Backup Scheduler + Restore Runbook

## Scope

Automated backup flow in `app/services/backup_scheduler.py` and admin scheduler endpoints.

## State machine

- `disabled`
- `monitoring`
- `countdown`
- `stopping_server`
- `compressing`
- `uploading`
- `restarting`
- `error`

## Preconditions

- `drive_folder_id` configured
- `config_files/service_account_backup.json` present
- Google Drive connection test success

## Default flow

1. Countdown warning if players online
2. Stop server
3. Compress server directory to `.zip`
4. Upload to Drive
5. Optional prune old backups (`keep_drive_backups`)
6. Restart server

## Coordination rule

- Backup scheduler skips action when reboot scheduler is in active non-monitoring state.

## Failure behavior

- If upload/compress fails, scheduler enters `error`.
- Local archive is kept for manual upload when failure occurs.
- If server was running, scheduler still attempts restart in `finally` block.

## Restore quick checklist

1. Pick backup by timestamp/version in Drive.
2. Stop current server.
3. Replace server directory with restored archive content.
4. Verify critical files:
  - world data
  - `plugins/`
  - `server.properties`
  - whitelist and permission data
5. Start server and verify:
  - RCON health
  - plugin load
  - player join path

## Do not

- Do not run restore while auto schedulers are actively executing.
- Do not overwrite live files without a rollback copy of the current state.
