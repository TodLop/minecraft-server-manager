# app/routers/admin_server.py
"""
Admin Server Control, Console, Log, and WebSocket Endpoints

Extracted from admin.py for modularity.
"""

import asyncio
import gzip
import logging
import re
import secrets
import time
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR, APP_VERSION
from app.core.minecraft_access import require_minecraft_admin
from app.services import minecraft_updater
from app.services import minecraft_server

# Audit logger for admin actions
admin_audit_logger = logging.getLogger("admin_audit")
admin_audit_logger.setLevel(logging.INFO)
if not admin_audit_logger.handlers:
    from pathlib import Path
    _logs_dir = Path("logs")
    _logs_dir.mkdir(exist_ok=True)
    _handler = logging.FileHandler(_logs_dir / "admin_audit.log")
    _handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    admin_audit_logger.addHandler(_handler)

# RCON command security
# NOTE: OP/DEOP are intentionally left commented for now (temporarily allowed for admin console operations).
DANGEROUS_COMMANDS = frozenset({
    "stop",
    # "op",
    # "deop",
    "ban-ip",
    "pardon-ip",
})
_command_rate_limits: dict = {}  # email -> list of timestamps
COMMAND_RATE_LIMIT = 10  # max commands per minute
COMMAND_RATE_WINDOW = 60  # seconds

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/api/minecraft/status")
async def get_minecraft_status(user_info: dict = Depends(require_minecraft_admin)):
    """Get Minecraft server status and plugin versions"""
    versions_data = minecraft_updater.load_versions()
    server_status = minecraft_updater.get_server_status()

    return JSONResponse({
        "status": "ok",
        "minecraft_version": versions_data.get("minecraft_version"),
        "last_check": versions_data.get("last_check"),
        "plugins": versions_data.get("plugins", {}),
        "server": server_status
    })


@router.get("/console", response_class=HTMLResponse)
async def minecraft_console(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Minecraft server console page"""
    server_status = minecraft_server.get_server_status()
    rcon_config = minecraft_server.get_rcon_config()

    return templates.TemplateResponse("admin/console.html", {
        "request": request,
        "user_info": user_info,
        "is_admin": True,
        "server_status": server_status,
        "rcon_enabled": rcon_config.enabled
    })


@router.get("/log", response_class=HTMLResponse)
async def minecraft_dev_log(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Developer-only raw log viewer page"""
    return templates.TemplateResponse("admin/log.html", {
        "request": request,
        "user_info": user_info,
        "is_admin": True
    })


@router.get("/api/minecraft/server/status")
async def get_server_status(user_info: dict = Depends(require_minecraft_admin)):
    """Get detailed server running status"""
    status = minecraft_server.get_server_status()
    rcon_config = minecraft_server.get_rcon_config()

    return JSONResponse({
        "status": "ok",
        "server": {
            "running": status.running,
            "process_running": status.process_running,
            "healthy": status.healthy,
            "state_reason": status.state_reason,
            "pid": status.pid,
            "game_port_listening": status.game_port_listening,
            "rcon_port_listening": status.rcon_port_listening,
            "players_online": status.players_online,
            "max_players": status.max_players,
            "version": status.version,
        },
        "rcon": {
            "enabled": rcon_config.enabled,
            "port": rcon_config.port
        }
    })


@router.get("/api/minecraft/players")
async def get_admin_online_players(user_info: dict = Depends(require_minecraft_admin)):
    """Get list of online players for admin panel"""
    status = minecraft_server.get_server_status()
    if not status.running:
        return JSONResponse({"status": "ok", "players": [], "message": "Server offline"})

    try:
        result = await minecraft_server.send_command("list")
        if result.get("success") and result.get("response"):
            response = result["response"]
            players = []
            if ":" in response:
                players_part = response.split(":")[-1].strip()
                if players_part:
                    players = [p.strip() for p in players_part.split(",") if p.strip()]

            return JSONResponse({
                "status": "ok",
                "players": players,
                "count": len(players)
            })
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    return JSONResponse({"status": "ok", "players": [], "count": 0})


@router.post("/api/minecraft/server/start")
async def start_server(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Start the Minecraft server"""
    from app.services.operations import execute_operation
    result = await execute_operation(
        key="server:start",
        user_info=user_info,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return JSONResponse(result)


@router.post("/api/minecraft/server/stop")
async def stop_server(request: Request, force: bool = False, user_info: dict = Depends(require_minecraft_admin)):
    """Stop the Minecraft server"""
    from app.services.operations import execute_operation
    result = await execute_operation(
        key="server:stop",
        user_info=user_info,
        params={"force": force},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return JSONResponse(result)


@router.post("/api/minecraft/server/restart")
async def restart_server(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Restart the Minecraft server"""
    from app.services.operations import execute_operation
    result = await execute_operation(
        key="server:restart",
        user_info=user_info,
        params={"source": "admin_ui"},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return JSONResponse(result)


@router.post("/api/minecraft/server/recover")
async def recover_server(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Emergency recovery when UI/server state diverges."""
    from app.services.operations import execute_operation
    result = await execute_operation(
        key="server:recover",
        user_info=user_info,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return JSONResponse(result)


@router.post("/api/minecraft/server/command")
async def send_server_command(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Send a command to the Minecraft server (with audit logging, denylist, and rate limiting)"""
    body = await request.json()
    command = body.get("command", "").strip()
    admin_email = user_info.get("email", "unknown")

    if not command:
        return JSONResponse({"success": False, "error": "No command provided"}, status_code=400)

    # Sanitize: strip control characters, cap length
    command = re.sub(r'[\x00-\x1f\x7f]', '', command)[:256]

    # Denylist: disabled - admins/staff need full command access
    # base_command = command.split()[0].lstrip("/").lower() if command.split() else ""
    # if base_command in DANGEROUS_COMMANDS:
    #     admin_audit_logger.warning(
    #         f"BLOCKED | admin={admin_email} | action=rcon_command | command={command[:100]} | reason=dangerous_command"
    #     )
    #     return JSONResponse({
    #         "success": False,
    #         "error": f"Command '{base_command}' is blocked. Use the dedicated endpoint instead."
    #     }, status_code=403)

    from app.services.rate_limit import check_rate_limit
    allowed, retry_after = check_rate_limit(
        bucket="rcon_command",
        key=admin_email,
        limit=COMMAND_RATE_LIMIT,
        window_seconds=COMMAND_RATE_WINDOW,
    )
    if not allowed:
        from app.services.audit_log import audit_event
        audit_event(logger=admin_audit_logger, actor=admin_email, action="rcon_command", target="rate_limit", result="denied")
        return JSONResponse(
            {"success": False, "error": f"Rate limit exceeded. Retry after {retry_after}s"},
            status_code=429,
        )

    from app.services.rcon_policy import decide_rcon_command
    decision = decide_rcon_command(command=command, dangerous_commands=set(DANGEROUS_COMMANDS))
    if not decision.allowed:
        from app.services.audit_log import audit_event
        audit_event(
            logger=admin_audit_logger,
            actor=admin_email,
            action="rcon_command",
            target=decision.base_command,
            result="blocked",
            extra={"reason": decision.reason},
        )
        return JSONResponse(
            {"success": False, "error": f"Command '{decision.base_command}' is blocked. Use dedicated endpoints."},
            status_code=403,
        )

    from app.services.audit_log import audit_event
    audit_event(
        logger=admin_audit_logger,
        actor=admin_email,
        action="rcon_command",
        target=decision.base_command,
        result="allowed",
    )

    result = await minecraft_server.send_command(command)
    return JSONResponse(result)


@router.get("/api/minecraft/server/logs")
async def get_server_logs(lines: int = 100, offset: int = 0, user_info: dict = Depends(require_minecraft_admin)):
    """Get server console logs with pagination support"""
    # Try to get live logs first, fall back to file
    logs = minecraft_server.get_recent_logs(lines, offset=offset)

    if not logs and offset == 0:
        # Fall back to latest.log file only for initial load
        logs = minecraft_server.read_latest_log(lines)

    return JSONResponse({
        "status": "ok",
        "count": len(logs),
        "logs": logs,
        "has_more": len(logs) == lines  # If we got full page, there might be more
    })


@router.get("/api/minecraft/server/full-log")
async def get_full_server_log(user_info: dict = Depends(require_minecraft_admin)):
    """Get FULL server log from latest.log file (for developer debugging)"""
    logs = minecraft_server.read_latest_log(lines=10000)  # Get up to 10000 lines
    return JSONResponse({
        "status": "ok",
        "count": len(logs),
        "logs": logs
    })


@router.get("/api/minecraft/server/log-files")
async def list_log_files(user_info: dict = Depends(require_minecraft_admin)):
    """List all available log files (latest.log and archived .gz files)"""
    logs_dir = minecraft_server.SERVER_DIR / "logs"
    log_files = []

    if logs_dir.exists():
        # Add latest.log first
        latest = logs_dir / "latest.log"
        if latest.exists():
            stat = latest.stat()
            log_files.append({
                "name": "latest.log",
                "size": stat.st_size,
                "modified": stat.st_mtime
            })

        # Add archived .gz files sorted by date (newest first)
        gz_files = sorted(logs_dir.glob("*.log.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in gz_files[:200]:  # Limit to last 200 archived logs
            stat = f.stat()
            log_files.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime
            })

    return JSONResponse({"status": "ok", "files": log_files})


@router.get("/api/minecraft/server/log-file/{filename:path}")
async def get_log_file(filename: str, user_info: dict = Depends(require_minecraft_admin)):
    """Load a specific log file by name (supports .gz files)"""
    logs_dir = minecraft_server.SERVER_DIR / "logs"
    log_path = logs_dir / filename

    # Security check: ensure path is within logs directory
    try:
        log_path.resolve().relative_to(logs_dir.resolve())
    except ValueError:
        return JSONResponse({"status": "error", "message": "Invalid file path"}, status_code=400)

    if not log_path.exists():
        return JSONResponse({"status": "error", "message": "File not found"}, status_code=404)

    logs = []
    try:
        if filename.endswith('.gz'):
            with gzip.open(log_path, 'rt', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        else:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

        for line in lines:  # Return ALL logs from the file
            line = line.strip()
            if not line:
                continue
            # Parse time from log line
            time_match = None
            if line.startswith('['):
                import re
                time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]', line)

            logs.append({
                "time": time_match.group(1) if time_match else "",
                "message": line
            })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    return JSONResponse({
        "status": "ok",
        "filename": filename,
        "count": len(logs),
        "logs": logs
    })


@router.websocket("/ws/minecraft/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming"""
    await websocket.accept()

    log_queue = asyncio.Queue()
    sent_logs = set()  # Track sent log hashes to prevent duplicates

    async def log_callback(log_entry):
        # Create a hash of the log entry for deduplication
        log_hash = f"{log_entry.get('time', '')}:{log_entry.get('message', '')}"
        if log_hash not in sent_logs:
            await log_queue.put(log_entry)

    # Subscribe FIRST to not miss any logs during initial send
    minecraft_server.subscribe_to_logs(log_callback)

    try:
        # Send recent logs and track what we sent
        recent = minecraft_server.get_recent_logs(50)
        for log in recent:
            log_hash = f"{log.get('time', '')}:{log.get('message', '')}"
            sent_logs.add(log_hash)
            await websocket.send_json(log)

        # Stream new logs (only those not already sent)
        while True:
            try:
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                log_hash = f"{log_entry.get('time', '')}:{log_entry.get('message', '')}"
                if log_hash not in sent_logs:
                    sent_logs.add(log_hash)
                    await websocket.send_json(log_entry)
                    # Limit size of tracking set
                    if len(sent_logs) > 1000:
                        sent_logs.clear()
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        pass
    finally:
        minecraft_server.unsubscribe_from_logs(log_callback)


@router.websocket("/ws/minecraft/raw-logs")
async def websocket_raw_logs(websocket: WebSocket):
    """WebSocket endpoint for RAW log streaming (no filtering, for dev log viewer)"""
    await websocket.accept()

    log_queue = asyncio.Queue()
    sent_logs = set()

    async def log_callback(log_entry):
        log_hash = f"{log_entry.get('time', '')}:{log_entry.get('message', '')}"
        if log_hash not in sent_logs:
            await log_queue.put(log_entry)

    minecraft_server.subscribe_to_logs(log_callback)

    try:
        # Send ALL recent logs (unfiltered, more lines for debugging)
        recent = minecraft_server.get_recent_logs(200, filtered=False)
        for log in recent:
            log_hash = f"{log.get('time', '')}:{log.get('message', '')}"
            sent_logs.add(log_hash)
            await websocket.send_json(log)

        # Stream new logs without filtering
        while True:
            try:
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                log_hash = f"{log_entry.get('time', '')}:{log_entry.get('message', '')}"
                if log_hash not in sent_logs:
                    sent_logs.add(log_hash)
                    await websocket.send_json(log_entry)
                    if len(sent_logs) > 2000:
                        sent_logs.clear()
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        pass
    finally:
        minecraft_server.unsubscribe_from_logs(log_callback)


# =============================================================================
# Full Update Flow (with server control)
# =============================================================================

@router.post("/api/minecraft/update/{plugin_id}")
async def apply_plugin_update(plugin_id: str, user_info: dict = Depends(require_minecraft_admin)):
    """
    Apply update for a specific plugin

    Requires prior update check to populate pending update info.
    """
    try:
        # First check for the latest version
        versions_data = minecraft_updater.load_versions()
        plugin_config = versions_data.get("plugins", {}).get(plugin_id)

        if not plugin_config:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found in tracking")

        minecraft_version = versions_data.get("minecraft_version", "1.21.1")

        # Check for update
        update_check = await minecraft_updater.check_plugin_update(
            plugin_id, plugin_config, minecraft_version
        )

        if not update_check.has_update:
            return JSONResponse({
                "status": "no_update",
                "message": f"{plugin_id} is already up to date (v{update_check.current_version})"
            })

        # Apply the update
        log = await minecraft_updater.apply_update(plugin_id, update_check)

        return JSONResponse({
            "status": log.status,
            "plugin_id": plugin_id,
            "from_version": log.from_version,
            "to_version": log.to_version,
            "steps": log.steps,
            "error": log.error
        })

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "error": str(e)
        }, status_code=500)


@router.post("/api/minecraft/update-with-restart/{plugin_id}")
async def apply_update_with_restart(plugin_id: str, user_info: dict = Depends(require_minecraft_admin)):
    """
    Full update flow: stop server -> apply update -> start server
    """
    steps = []
    server_was_running = minecraft_server.is_server_running()

    try:
        # Step 1: Stop server if running
        if server_was_running:
            steps.append({"step": "stop_server", "status": "started"})
            stop_result = await minecraft_server.stop_server()
            if not stop_result["success"]:
                steps.append({"step": "stop_server", "status": "failed", "error": stop_result.get("error")})
                return JSONResponse({
                    "status": "failed",
                    "error": f"Failed to stop server: {stop_result.get('error')}",
                    "steps": steps
                }, status_code=500)
            steps.append({"step": "stop_server", "status": "completed"})
            await asyncio.sleep(3)

        # Step 2: Apply update
        steps.append({"step": "apply_update", "status": "started"})

        versions_data = minecraft_updater.load_versions()
        plugin_config = versions_data.get("plugins", {}).get(plugin_id)

        if not plugin_config:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        minecraft_version = versions_data.get("minecraft_version", "1.21.11")
        update_check = await minecraft_updater.check_plugin_update(
            plugin_id, plugin_config, minecraft_version
        )

        if not update_check.has_update:
            steps.append({"step": "apply_update", "status": "skipped", "reason": "already up to date"})
        else:
            update_log = await minecraft_updater.apply_update(plugin_id, update_check)
            if update_log.status != "success":
                steps.append({"step": "apply_update", "status": "failed", "error": update_log.error})
                return JSONResponse({
                    "status": "failed",
                    "error": f"Update failed: {update_log.error}",
                    "steps": steps
                }, status_code=500)
            steps.append({
                "step": "apply_update",
                "status": "completed",
                "from_version": update_log.from_version,
                "to_version": update_log.to_version
            })

        # Step 3: Restart server if it was running
        if server_was_running:
            steps.append({"step": "start_server", "status": "started"})
            await asyncio.sleep(2)

            start_result = await minecraft_server.start_server()
            if not start_result["success"]:
                steps.append({"step": "start_server", "status": "failed", "error": start_result.get("error")})
                return JSONResponse({
                    "status": "partial",
                    "message": "Update applied but server failed to start",
                    "error": start_result.get("error"),
                    "steps": steps
                }, status_code=500)
            steps.append({"step": "start_server", "status": "completed", "pid": start_result.get("pid")})

        return JSONResponse({
            "status": "success",
            "message": f"Update completed" + (" and server restarted" if server_was_running else ""),
            "steps": steps
        })

    except HTTPException:
        raise
    except Exception as e:
        steps.append({"step": "error", "error": str(e)})
        return JSONResponse({
            "status": "failed",
            "error": str(e),
            "steps": steps
        }, status_code=500)


@router.post("/api/minecraft/check-updates")
async def trigger_update_check(user_info: dict = Depends(require_minecraft_admin)):
    """Manually trigger update check for all tracked plugins"""
    try:
        results = await minecraft_updater.check_all_updates()

        # Convert to serializable format
        updates = []
        for result in results:
            updates.append({
                "plugin_id": result.plugin_id,
                "source": result.source,
                "current_version": result.current_version,
                "latest_version": result.latest_version,
                "has_update": result.has_update,
                "download_url": result.download_url,
                "filename": result.filename,
                "changelog": result.changelog[:500] if result.changelog else None,
                "current_full_version": result.current_full_version,
                "latest_full_version": result.latest_full_version
            })

        return JSONResponse({
            "status": "ok",
            "checked_at": minecraft_updater.load_versions().get("last_check"),
            "updates": updates,
            "updates_available": sum(1 for u in updates if u["has_update"])
        })

    except Exception as e:
        return JSONResponse({
            "status": "error",
            "error": str(e)
        }, status_code=500)


@router.get("/api/minecraft/logs")
async def get_update_logs(limit: int = 20, user_info: dict = Depends(require_minecraft_admin)):
    """Get recent update operation logs"""
    logs = minecraft_updater.get_update_logs(limit=limit)
    return JSONResponse({
        "status": "ok",
        "count": len(logs),
        "logs": logs
    })


@router.get("/api/minecraft/update-logs")
async def get_update_logs_api(limit: int = 10, user_info: dict = Depends(require_minecraft_admin)):
    """Get update logs via API for Alpine.js"""
    logs = minecraft_updater.get_update_logs(limit=limit)
    return JSONResponse({
        "status": "ok",
        "logs": logs
    })


@router.get("/api/minecraft/changelog/{plugin_id}")
async def get_plugin_changelog(plugin_id: str, user_info: dict = Depends(require_minecraft_admin)):
    """Get changelog for a specific plugin's latest version"""
    try:
        versions_data = minecraft_updater.load_versions()
        plugin_config = versions_data.get("plugins", {}).get(plugin_id)

        if not plugin_config:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        minecraft_version = versions_data.get("minecraft_version", "1.21.1")

        # Get latest version info
        source = plugin_config.get("source")
        project_id = plugin_config.get("project_id", plugin_id)

        if source == "papermc":
            version_info = await minecraft_updater.get_papermc_latest(minecraft_version)
        elif source == "modrinth":
            version_info = await minecraft_updater.get_modrinth_latest(project_id, minecraft_version)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

        return JSONResponse({
            "status": "ok",
            "plugin_id": plugin_id,
            "version": version_info.version,
            "changelog": version_info.changelog,
            "game_versions": version_info.game_versions
        })

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "error": str(e)
        }, status_code=500)


@router.post("/api/minecraft/server/enable-rcon")
async def enable_rcon_endpoint(user_info: dict = Depends(require_minecraft_admin)):
    """Enable RCON in server.properties - requires server restart"""

    # Generate a secure password
    password = secrets.token_urlsafe(16)

    success = minecraft_server.enable_rcon(password)

    if success:
        return JSONResponse({
            "success": True,
            "message": "RCON enabled in server.properties. Restart the server to apply.",
            "password": password,
            "requires_restart": True
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to enable RCON. server.properties not found."
        }, status_code=500)
