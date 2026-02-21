---
title: Minecraft Backend Operations Runbook
audience: privileged_staff
owner: operations-lead
last_reviewed_at: 2026-02-18
tags:
  - runbook
  - governance
---
# Minecraft Backend Operations Runbook

This section is the operations source of truth for backend behavior that may look like a bug without context.

## Access policy

- Admin: all documents
- Staff: only with `ops:backend_docs:view`
- Additional document-level filter:
  - `audience: privileged_staff` -> visible to permissioned staff
  - `audience: admin_only` -> hidden from staff (returns 404)

## Core document index (8)

- `000-restart-control` (staff visible)
- `010-restart-troubleshooting` (staff visible)
- `020-reboot-scheduler-state-machine` (staff visible)
- `030-backup-scheduler-restore-runbook` (staff visible)
- `040-operations-api-contract-idempotency` (admin only)
- `050-rbac-operations-and-handover` (admin only)
- `060-coreprotect-retention-purge-policy` (admin only)
- `070-incident-response-escalation-playbook` (staff visible)

## Update workflow

- Edit markdown under `docs/minecraft/backend/`.
- Keep front matter accurate (`owner`, `last_reviewed_at`, `audience`, `tags`).
- If code logic changes, update the related runbook in the same change set.

## Minimum document contract

- Scope and trigger paths (admin UI, staff UI, scheduler, automation)
- Expected states and API error codes
- Operational do/don't guidance
- Escalation path and rollback/safety notes
