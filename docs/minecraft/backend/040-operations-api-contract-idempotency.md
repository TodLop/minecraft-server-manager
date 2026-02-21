---
title: 040 Operations API Contract + Idempotency
audience: admin_only
owner: backend-admin
last_reviewed_at: 2026-02-18
tags:
  - operations-api
  - idempotency
  - reliability
---
# 040 Operations API Contract + Idempotency

## Scope

Operation execution contract in `app/services/operations.py`.

## Registry model

Operations are defined via `OperationSpec` registry with:

- operation key
- required permission
- admin-only flag
- risk level
- preflight
- executor

Current keys include:

- `server:start`
- `server:restart`
- `server:stop`
- `server:recover`

## Rate limiting

- Bucket: `operations`
- Limit: `10` per `60s` per actor+operation
- Violations return HTTP `429`.

## Idempotency contract

- Optional header: `Idempotency-Key`
- Cache key shape: `{op_key}:{actor}:{idempotency_key}`
- TTL: `OPERATIONS_IDEMPOTENCY_TTL_SECONDS` (default `900`)
- If same key is in progress:
  - `success: false`
  - `status: in_progress`
  - `idempotent_replay: true`
- If completed:
  - returns cached result with `idempotent_replay: true`

## Persistent operation trace

- File: `data/history/operation_state.jsonl`
- Logs `started` + final `succeeded|failed` records
- Includes actor, op id, idempotency key, timestamps, error

## Restart source discipline

- `server:restart` should pass source (`admin_ui`, `staff_ui`, `auto_scheduler`, etc.)
- Source is used by downstream restart diagnostics and cooldown reasoning.

## Change safety rules

- Any contract changes require:
  - runbook update
  - regression tests for replay/in-progress behaviors
