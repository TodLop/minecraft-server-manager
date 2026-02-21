---
title: 050 RBAC Operations and Handover Guide
audience: admin_only
owner: backend-admin
last_reviewed_at: 2026-02-18
tags:
  - rbac
  - permissions
  - handover
---
# 050 RBAC Operations and Handover Guide

## Scope

RBAC internals and operational handover policy for Minecraft staff access.

## Core model

- Source file: `app/services/permissions.py`
- Effective permission formula:
  - `(role_permissions | grants) - revokes`
- Persisted in:
  - `data/rbac_settings.json`

## Admin interfaces

- API routes in `app/routers/admin_rbac.py`
- Staff dashboard fetches effective permissions and visible modules dynamically.

## Key operational controls

- Role assignment
- Per-user grant/revoke overrides
- Full reset to clear role+overrides

## Audit trail

- RBAC actions logged to `logs/rbac_audit.log`
- Expected event categories:
  - `ROLE_CHANGE`
  - `GRANT`
  - `REVOKE`
  - `RESET`

## Handover minimum

- At least one non-owner senior operator must retain:
  - restart-related permissions
  - `ops:backend_docs:view`
  - incident response runbook familiarity

## Safety notes

- Admin bypass is intentional and must remain limited to trusted admin emails.
- Do not grant broad permissions to all staff by default.
- Use explicit grants for sensitive operations.
