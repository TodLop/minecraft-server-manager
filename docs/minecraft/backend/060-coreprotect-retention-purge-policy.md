---
title: 060 CoreProtect Retention and Purge Policy
audience: admin_only
owner: backend-admin
last_reviewed_at: 2026-02-18
tags:
  - coreprotect
  - retention
  - maintenance
---
# 060 CoreProtect Retention and Purge Policy

## Scope

Automated and manual CoreProtect purge logic in reboot scheduler.

## Config keys

- `coreprotect_purge_enabled`
- `coreprotect_retention_days` (default `30`)
- `coreprotect_purge_hour` (default `4`)
- `coreprotect_last_purge`

## Schedule semantics

- Purge runs only when:
  - scheduler enabled
  - server running
  - current hour matches configured purge hour
  - no purge already run on current date

## Execution sequence

1. `co purge t:{retention_days}d`
2. wait ~2 seconds
3. `co purge t:{retention_days}d confirm`

## Manual trigger path

- Admin endpoint: `POST /api/minecraft/coreprotect/purge`
- Uses same safety checks and logs.

## Monitoring points

- status fields:
  - `purge_running`
  - `last_purge`
  - `next_purge`
- scheduler logs:
  - `coreprotect_purge_started`
  - `coreprotect_purge_completed`
  - `coreprotect_purge_failed`

## Risk notes

- Aggressive retention values can remove investigation data needed for moderation cases.
- Change retention only with moderation/admin agreement.
