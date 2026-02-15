from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException

from app.core.auth import is_admin
from app.core.config import HISTORY_DIR
from app.services import minecraft_server
from app.services import permissions as permissions_service
from app.services.rate_limit import check_rate_limit


PreflightFn = Callable[[dict, dict[str, Any]], tuple[bool, str]]
ExecutorFn = Callable[[dict, dict[str, Any]], Awaitable[dict]]

_IDEMPOTENCY_TTL_SECONDS = int(os.getenv("OPERATIONS_IDEMPOTENCY_TTL_SECONDS", "900"))
_IDEMPOTENCY_LOCK = threading.Lock()
_IDEMPOTENCY_CACHE: dict[str, dict[str, Any]] = {}

_OPERATION_STATE_FILE = HISTORY_DIR / "operation_state.jsonl"
_OPERATION_STATE_LOCK = threading.Lock()


class OperationNotFound(Exception):
    pass


def _cleanup_expired_idempotency_entries(now: float) -> None:
    expired_keys = [
        cache_key
        for cache_key, entry in _IDEMPOTENCY_CACHE.items()
        if float(entry.get("expires_at", 0)) <= now
    ]
    for cache_key in expired_keys:
        _IDEMPOTENCY_CACHE.pop(cache_key, None)


def _append_operation_state(record: dict[str, Any]) -> None:
    state_file: Path = _OPERATION_STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with _OPERATION_STATE_LOCK:
        with state_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class OperationSpec:
    key: str
    required_permission: Optional[str]
    admin_only: bool
    risk: str
    preflight: PreflightFn
    executor: ExecutorFn


def _preflight_always_ok(user_info: dict, params: dict[str, Any]) -> tuple[bool, str]:
    return True, ""


async def _exec_server_start(user_info: dict, params: dict[str, Any]) -> dict:
    return await minecraft_server.start_server()


async def _exec_server_restart(user_info: dict, params: dict[str, Any]) -> dict:
    return await minecraft_server.restart_server()


async def _exec_server_stop(user_info: dict, params: dict[str, Any]) -> dict:
    force = bool(params.get("force", False))
    return await minecraft_server.stop_server(force=force)


_REGISTRY: dict[str, OperationSpec] = {
    "server:start": OperationSpec(
        key="server:start",
        required_permission="server:start",
        admin_only=False,
        risk="medium",
        preflight=_preflight_always_ok,
        executor=_exec_server_start,
    ),
    "server:restart": OperationSpec(
        key="server:restart",
        required_permission="server:restart",
        admin_only=False,
        risk="medium",
        preflight=_preflight_always_ok,
        executor=_exec_server_restart,
    ),
    "server:stop": OperationSpec(
        key="server:stop",
        required_permission="server:stop",
        admin_only=True,
        risk="high",
        preflight=_preflight_always_ok,
        executor=_exec_server_stop,
    ),
}


def get_operation_spec(key: str) -> OperationSpec:
    spec = _REGISTRY.get(key)
    if spec is None:
        raise OperationNotFound(key)
    return spec


async def execute_operation(
    *,
    key: str,
    user_info: dict,
    params: Optional[dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    params = params or {}
    spec = get_operation_spec(key)

    actor_email = user_info.get("email", "")
    actor_name = user_info.get("name", "")
    actor_label = actor_email or actor_name or "unknown"
    actor_is_admin = is_admin(user_info)

    allowed, retry_after = check_rate_limit(
        bucket="operations",
        key=f"{actor_email}:{spec.key}",
        limit=10,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Retry after {retry_after}s")

    if spec.admin_only and not actor_is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if spec.required_permission and not actor_is_admin:
        if not permissions_service.has_permission(actor_email, spec.required_permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {spec.required_permission}")

    ok, error = spec.preflight(user_info, params)
    if not ok:
        return {"success": False, "error": error or "Preflight failed"}

    normalized_idempotency_key = (idempotency_key or "").strip() or None
    idempotency_cache_key = ""
    now = time.time()

    if normalized_idempotency_key:
        idempotency_cache_key = f"{spec.key}:{actor_label}:{normalized_idempotency_key}"
        with _IDEMPOTENCY_LOCK:
            _cleanup_expired_idempotency_entries(now)
            existing_entry = _IDEMPOTENCY_CACHE.get(idempotency_cache_key)
            if existing_entry:
                if existing_entry.get("status") == "done":
                    cached_result = dict(existing_entry.get("result") or {"success": False, "error": "Unknown idempotency replay result"})
                    cached_result["idempotent_replay"] = True
                    return cached_result
                return {
                    "success": False,
                    "error": "Operation already in progress for this idempotency key",
                    "status": "in_progress",
                    "idempotent_replay": True,
                }

            _IDEMPOTENCY_CACHE[idempotency_cache_key] = {
                "status": "in_progress",
                "expires_at": now + _IDEMPOTENCY_TTL_SECONDS,
                "result": None,
            }

    op_id = str(uuid.uuid4())
    started_at = int(time.time())
    base_state: dict[str, Any] = {
        "op_key": spec.key,
        "op_id": op_id,
        "actor": actor_label,
        "idempotency_key": normalized_idempotency_key,
        "started_at": started_at,
    }
    _append_operation_state({
        **base_state,
        "finished_at": None,
        "status": "started",
        "error": "",
    })

    try:
        result = await spec.executor(user_info, params)
    except Exception as exc:
        finished_at = int(time.time())
        error_message = str(exc) or "Operation execution failed"
        failure_result = {"success": False, "error": error_message}
        _append_operation_state({
            **base_state,
            "finished_at": finished_at,
            "status": "failed",
            "error": error_message,
        })
        if normalized_idempotency_key:
            with _IDEMPOTENCY_LOCK:
                _IDEMPOTENCY_CACHE[idempotency_cache_key] = {
                    "status": "done",
                    "expires_at": finished_at + _IDEMPOTENCY_TTL_SECONDS,
                    "result": failure_result,
                }
        return failure_result

    finished_at = int(time.time())
    success = bool(result.get("success")) if isinstance(result, dict) else False
    error_message = ""
    if not success:
        if isinstance(result, dict):
            error_message = str(result.get("error", ""))
        else:
            error_message = "Operation execution failed"
    _append_operation_state({
        **base_state,
        "finished_at": finished_at,
        "status": "succeeded" if success else "failed",
        "error": error_message,
    })

    if normalized_idempotency_key:
        with _IDEMPOTENCY_LOCK:
            _IDEMPOTENCY_CACHE[idempotency_cache_key] = {
                "status": "done",
                "expires_at": finished_at + _IDEMPOTENCY_TTL_SECONDS,
                "result": result,
            }

    return result
