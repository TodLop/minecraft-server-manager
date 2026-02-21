---
title: 010 Restart Troubleshooting
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - restart
  - troubleshooting
  - rcon
---
# 010 Restart Troubleshooting

## Symptom: announcement worked but restart did not continue

Example path:

- RCON broadcast was delivered.
- Follow-up restart command did not execute as expected.
- A manual admin panel restart succeeded.

## First checks

- Confirm the response payload from restart endpoint:
  - `error_code: restart_in_progress`
  - `error_code: restart_cooldown`
- Confirm whether another actor triggered restart near the same timestamp:
  - admin UI
  - staff UI
  - scheduler token execution

## Expected behavior with current guardrails

- If another restart is active, new request is denied (`restart_in_progress`).
- If a restart just completed, new request is denied for 120 seconds (`restart_cooldown`).
- Scheduler should treat cooldown denial as a skip and return to monitoring state.

## Incident triage checklist

- Collect timestamps for:
  - warning broadcast sent
  - restart request attempted
  - restart completion timestamp
- Check scheduler log actions around the same time.
- Verify no rapid repeated clicks in admin or staff UI.

## Recovery actions

- Wait until cooldown expires and retry once.
- Avoid repeated manual retries during cooldown window.
- If restart remains blocked beyond cooldown:
  - inspect operation-state log entries
  - inspect server manager health checks
  - escalate to admin-level code review

## Known non-bug states

- Immediate second restart is rejected by design.
- Manual restart succeeding after cooldown while automation failed inside cooldown is expected.
