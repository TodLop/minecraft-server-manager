---
title: 070 Incident Response Escalation Playbook
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - incident
  - escalation
  - operations
---
# 070 Incident Response Escalation Playbook

## Scope

Shared response flow for restart/backup/scheduler incidents.

## Triage order (first 5 minutes)

1. Identify current impact:
  - server offline
  - restart loop
  - scheduler stuck
  - backup failed
2. Capture timestamps and actor path:
  - admin UI / staff UI / auto scheduler
3. Check most recent API result payload and `error_code`.
4. Check scheduler status and latest logs.

## Severity guideline

- P1:
  - server unavailable to players
  - repeated failed restarts with no recovery
- P2:
  - automation failed but manual recovery available
- P3:
  - expected guardrail rejection (cooldown/in-progress), no outage

## Immediate controls

- Avoid repeated manual restart clicks during cooldown.
- Cancel active countdown if wrong trigger fired.
- Pause non-critical interventions until current scheduler state stabilizes.

## Escalation path

- Staff -> privileged operator -> admin owner
- Escalate immediately when:
  - error persists after one safe retry window
  - conflicting scheduler states continue
  - data integrity risk is suspected

## Evidence checklist

- restart/backup scheduler status snapshot
- last 20 scheduler logs
- operation response payloads with error codes
- exact UTC timestamps for key actions

## Post-incident requirement

- Update relevant runbook file with:
  - failure pattern
  - confirmed root cause
  - preventive action taken
