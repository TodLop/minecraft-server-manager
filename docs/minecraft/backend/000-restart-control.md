---
title: "000 Restart Control: Dedup + Cooldown"
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - restart
  - cooldown
  - scheduler
---
# 000 Restart Control: Dedup + Cooldown

## Scope

This document defines how restart requests are accepted or rejected across:

- Admin restart button
- Staff restart button
- Automatic reboot scheduler
- Future automation flows that call the same restart operation

## Current policy

- Only one restart can run at a time.
- After a successful restart, new restart requests are blocked for 120 seconds.
- During cooldown, API returns:
  - `success: false`
  - `error_code: restart_cooldown`
  - `retry_after_seconds: <remaining>`
- If a restart is already executing, API returns:
  - `success: false`
  - `error_code: restart_in_progress`

## Why this exists

- Prevent overlapping restart paths from manual button clicks and scheduler triggers.
- Prevent double restart loops during unstable startup periods.
- Keep control flow deterministic for incident response.

## Operational implications

- A second restart request immediately after success is expected to fail for up to 120 seconds.
- This is not a server fault by itself.
- UI should surface remaining wait time from `retry_after_seconds`.

## What operators should check

- Did the previous restart complete less than 120 seconds ago?
- Was there already an in-flight restart (`restart_in_progress`)?
- Is the scheduler state back to monitoring after cooldown rejection?

## Change management note

If cooldown duration or error contract changes, update this file and `010-restart-troubleshooting` together.
