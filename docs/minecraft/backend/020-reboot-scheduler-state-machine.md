---
title: 020 Reboot Scheduler State Machine
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - scheduler
  - reboot
  - state-machine
---
# 020 Reboot Scheduler State Machine

## Scope

Behavior of automatic restart orchestration in `app/services/reboot_scheduler.py`.

## State model

- `disabled`
- `monitoring`
- `countdown_empty`
- `countdown_uptime`
- `restarting`
- `error`

## Trigger conditions (default)

- Empty-server trigger:
  - `empty_server_enabled=true`
  - `empty_hours_threshold=6.0`
- Uptime trigger:
  - `uptime_restart_enabled=true`
  - `max_uptime_hours=12.0`

## Countdown behavior

- Warning window: `countdown_minutes=5`
- Minute warnings from `warning_intervals` (default `[5, 3, 1]`)
- Warning message uses title + chat:
  - `§6[Auto-Restart] ...`

## Token-based stale request protection

- Every restart/countdown chain gets a token.
- If a newer request issues a new token, older flow is skipped as stale.
- This prevents overlapping countdown/restart executions.

## Backup scheduler coordination

- Reboot scheduler checks backup scheduler state.
- If backup scheduler is not `disabled|monitoring`, reboot actions are skipped for that cycle.

## Restart execution notes

- Calls `minecraft_server.restart_server(...)` with:
  - ready timeout
  - start retries
  - retry delay
  - source: `auto_scheduler` or `manual_scheduler`
- If result is `restart_in_progress` or `restart_cooldown`, scheduler logs `restart_skipped` and returns to monitoring.

## Operator checks

- Validate current scheduler state before manual restart actions.
- If stuck in `error`, inspect scheduler logs and recent restart responses first.
