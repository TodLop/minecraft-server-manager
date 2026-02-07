# app/routers/admin.py
"""
Admin Panel Routes

Access restricted to ADMIN_EMAILS (configured via environment variable)
"""

import asyncio
import re
import time
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR
from app.core.auth import require_admin, is_admin, get_current_user
from app.services import minecraft_updater
from app.services import minecraft_server

# Import from staff.py for reuse
from app.routers.staff import extract_username, PLAYER_NAME_PATTERN

router = APIRouter(prefix="/minecraft/admin", tags=["Admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/api/overview")
async def get_admin_overview(user_info: dict = Depends(require_admin)):
    """Get aggregated overview data for admin dashboard"""
    from app.services.reboot_scheduler import get_scheduler
    
    # Get server status
    server_status = minecraft_server.get_server_status()
    
    # Get versions data for last check time
    versions_data = minecraft_updater.load_versions()
    
    # Get scheduler status for uptime
    scheduler = get_scheduler()
    scheduler_status = scheduler.get_status()
    
    # Count active services
    active_services = 1  # Web app is always running
    if server_status.running:
        active_services += 1  # Minecraft server
    
    # Format uptime
    uptime_str = scheduler_status.get("uptime_formatted", "--")
    if not server_status.running:
        uptime_str = "Offline"
    
    return JSONResponse({
        "status": "ok",
        "active_services": active_services,
        "pending_updates": versions_data.get("pending_updates", 0),
        "uptime": uptime_str,
        "last_check": versions_data.get("last_check"),
        "server_running": server_status.running,
        "players_online": server_status.players_online or 0
    })


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def minecraft_dashboard(request: Request, user_info: dict = Depends(require_admin)):
    """Minecraft server management dashboard"""
    # Get current version data
    versions_data = minecraft_updater.load_versions()
    file_status = minecraft_updater.get_server_status()  # File-based status
    server_status = minecraft_server.get_server_status()  # Process-based status
    update_logs = minecraft_updater.get_update_logs(limit=10)

    return templates.TemplateResponse("admin/minecraft.html", {
        "request": request,
        "user_info": user_info,
        "is_admin": True,
        "versions_data": versions_data,
        "server_status": {
            **file_status,
            "running": server_status.running,
            "pid": server_status.pid,
            "players_online": server_status.players_online,
            "max_players": server_status.max_players
        },
        "update_logs": update_logs
    })


@router.get("/api/minecraft/status")
async def get_minecraft_status(user_info: dict = Depends(require_admin)):
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


@router.post("/api/minecraft/check-updates")
async def trigger_update_check(user_info: dict = Depends(require_admin)):
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


@router.post("/api/minecraft/update/{plugin_id}")
async def apply_plugin_update(plugin_id: str, user_info: dict = Depends(require_admin)):
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


@router.get("/api/minecraft/logs")
async def get_update_logs(limit: int = 20, user_info: dict = Depends(require_admin)):
    """Get recent update operation logs"""
    logs = minecraft_updater.get_update_logs(limit=limit)
    return JSONResponse({
        "status": "ok",
        "count": len(logs),
        "logs": logs
    })


@router.get("/api/minecraft/update-logs")
async def get_update_logs_api(limit: int = 10, user_info: dict = Depends(require_admin)):
    """Get update logs via API for Alpine.js"""
    logs = minecraft_updater.get_update_logs(limit=limit)
    return JSONResponse({
        "status": "ok",
        "logs": logs
    })


@router.get("/api/minecraft/changelog/{plugin_id}")
async def get_plugin_changelog(plugin_id: str, user_info: dict = Depends(require_admin)):
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


# =============================================================================
# Server Control Endpoints
# =============================================================================

@router.get("/console", response_class=HTMLResponse)
async def minecraft_console(request: Request, user_info: dict = Depends(require_admin)):
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
async def minecraft_dev_log(request: Request, user_info: dict = Depends(require_admin)):
    """Developer-only raw log viewer page"""
    return templates.TemplateResponse("admin/log.html", {
        "request": request,
        "user_info": user_info,
        "is_admin": True
    })


@router.get("/api/minecraft/server/status")
async def get_server_status(user_info: dict = Depends(require_admin)):
    """Get detailed server running status"""
    status = minecraft_server.get_server_status()
    rcon_config = minecraft_server.get_rcon_config()

    return JSONResponse({
        "status": "ok",
        "server": {
            "running": status.running,
            "pid": status.pid,
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
async def get_admin_online_players(user_info: dict = Depends(require_admin)):
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
async def start_server(user_info: dict = Depends(require_admin)):
    """Start the Minecraft server"""
    result = await minecraft_server.start_server()
    return JSONResponse(result)


@router.post("/api/minecraft/server/stop")
async def stop_server(force: bool = False, user_info: dict = Depends(require_admin)):
    """Stop the Minecraft server"""
    result = await minecraft_server.stop_server(force=force)
    return JSONResponse(result)


@router.post("/api/minecraft/server/restart")
async def restart_server(user_info: dict = Depends(require_admin)):
    """Restart the Minecraft server"""
    result = await minecraft_server.restart_server()
    return JSONResponse(result)


@router.post("/api/minecraft/server/command")
async def send_server_command(request: Request, user_info: dict = Depends(require_admin)):
    """Send a command to the Minecraft server"""
    body = await request.json()
    command = body.get("command", "").strip()

    if not command:
        return JSONResponse({"success": False, "error": "No command provided"}, status_code=400)

    result = await minecraft_server.send_command(command)
    return JSONResponse(result)


@router.get("/api/minecraft/server/logs")
async def get_server_logs(lines: int = 100, offset: int = 0, user_info: dict = Depends(require_admin)):
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
async def get_full_server_log(user_info: dict = Depends(require_admin)):
    """Get FULL server log from latest.log file (for developer debugging)"""
    logs = minecraft_server.read_latest_log(lines=10000)  # Get up to 10000 lines
    return JSONResponse({
        "status": "ok",
        "count": len(logs),
        "logs": logs
    })


@router.get("/api/minecraft/server/log-files")
async def list_log_files(user_info: dict = Depends(require_admin)):
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
async def get_log_file(filename: str, user_info: dict = Depends(require_admin)):
    """Load a specific log file by name (supports .gz files)"""
    import gzip
    
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

@router.post("/api/minecraft/update-with-restart/{plugin_id}")
async def apply_update_with_restart(plugin_id: str, user_info: dict = Depends(require_admin)):
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


# =============================================================================
# Reboot Automation Endpoints
# =============================================================================

from app.services.reboot_scheduler import get_scheduler


@router.get("/api/minecraft/reboot-scheduler/status")
async def get_reboot_scheduler_status(user_info: dict = Depends(require_admin)):
    """Get current reboot scheduler status"""
    scheduler = get_scheduler()
    return JSONResponse({
        "status": "ok",
        "config": scheduler.get_config(),
        "scheduler_status": scheduler.get_status()
    })


@router.get("/api/minecraft/reboot-scheduler/logs")
async def get_reboot_scheduler_logs(limit: int = 50, user_info: dict = Depends(require_admin)):
    """Get reboot scheduler action logs"""
    scheduler = get_scheduler()
    return JSONResponse({
        "status": "ok",
        "logs": scheduler.get_logs(limit=limit)
    })


@router.post("/api/minecraft/reboot-scheduler/config")
async def update_reboot_scheduler_config(request: Request, user_info: dict = Depends(require_admin)):
    """Update reboot scheduler configuration"""
    body = await request.json()
    scheduler = get_scheduler()

    # Validate and update config
    result = scheduler.update_config(**body)
    return JSONResponse(result)


@router.post("/api/minecraft/reboot-scheduler/trigger")
async def trigger_manual_restart(request: Request, user_info: dict = Depends(require_admin)):
    """Manually trigger a server restart with countdown"""
    body = await request.json()
    reason = body.get("reason", "manual")

    scheduler = get_scheduler()
    result = await scheduler.trigger_manual_restart(reason)

    return JSONResponse(result)


@router.post("/api/minecraft/reboot-scheduler/cancel")
async def cancel_restart_countdown(user_info: dict = Depends(require_admin)):
    """Cancel an active restart countdown"""
    scheduler = get_scheduler()
    result = scheduler.cancel_countdown()
    return JSONResponse(result)


# =============================================================================
# CoreProtect Maintenance Endpoints
# =============================================================================

@router.get("/api/minecraft/coreprotect/status")
async def get_coreprotect_status(user_info: dict = Depends(require_admin)):
    """Get CoreProtect purge status"""
    scheduler = get_scheduler()
    return JSONResponse({
        "status": "ok",
        **scheduler.get_coreprotect_status()
    })


@router.post("/api/minecraft/coreprotect/config")
async def update_coreprotect_config(request: Request, user_info: dict = Depends(require_admin)):
    """Update CoreProtect purge configuration"""
    body = await request.json()
    scheduler = get_scheduler()

    # Only allow CoreProtect-related config updates
    allowed_keys = [
        "coreprotect_purge_enabled",
        "coreprotect_retention_days",
        "coreprotect_purge_hour"
    ]
    filtered = {k: v for k, v in body.items() if k in allowed_keys}

    if not filtered:
        return JSONResponse({"success": False, "error": "No valid config keys provided"}, status_code=400)

    result = scheduler.update_config(**filtered)
    return JSONResponse({
        **result,
        "coreprotect": scheduler.get_coreprotect_status()
    })


@router.post("/api/minecraft/coreprotect/purge")
async def trigger_coreprotect_purge(user_info: dict = Depends(require_admin)):
    """Manually trigger CoreProtect log purge"""
    scheduler = get_scheduler()
    result = await scheduler.execute_coreprotect_purge(manual=True)
    return JSONResponse(result)


@router.post("/api/minecraft/server/enable-rcon")
async def enable_rcon_endpoint(user_info: dict = Depends(require_admin)):
    """Enable RCON in server.properties - requires server restart"""
    import secrets

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


# =============================================================================
# Admin Moderation Endpoints (Player Management)
# =============================================================================

# Rate limiting for broadcast (shared with staff but separate for admin)
_admin_broadcast_cooldowns: dict = {}
BROADCAST_COOLDOWN_SECONDS = 60


@router.post("/api/minecraft/kick")
async def admin_kick_player(request: Request, user_info: dict = Depends(require_admin)):
    """
    Kick a player from the server (admin access - no protected player filtering).
    """
    body = await request.json()
    player = extract_username(body.get("player", "").strip())
    reason = body.get("reason", "Kicked by admin").strip()

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    # Sanitize reason
    reason = reason[:100]
    reason = reason.replace('\n', ' ').replace('\r', ' ')
    reason = re.sub(r'[^\w\s.,!?\-]', '', reason)
    reason = ' '.join(reason.split())
    if not reason:
        reason = "Kicked by admin"

    # Admin can kick any player (no protected player check)
    command = f"kick {player} {reason}"
    result = await minecraft_server.send_command(command)

    if result.get("success"):
        return JSONResponse({
            "success": True,
            "message": f"Kicked {player}",
            "response": result.get("response", "")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to execute kick command")
        }, status_code=500)


@router.post("/api/minecraft/tempban")
async def admin_tempban_player(request: Request, user_info: dict = Depends(require_admin)):
    """
    Temporarily ban a player (admin access - no protected player filtering).
    """
    body = await request.json()
    player = extract_username(body.get("player", "").strip())
    duration = body.get("duration", "").strip()
    reason = body.get("reason", "Admin action").strip()

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    allowed_durations = ["1h", "6h", "24h", "7d"]
    if duration not in allowed_durations:
        return JSONResponse({
            "success": False,
            "error": f"Invalid duration. Allowed: {', '.join(allowed_durations)}"
        }, status_code=400)

    # Sanitize reason
    reason = reason[:100]
    reason = reason.replace('\n', ' ').replace('\r', ' ')
    reason = re.sub(r'[^\w\s.,!?\-]', '', reason)
    reason = ' '.join(reason.split())
    if not reason:
        reason = "Admin action"

    # Admin can ban any player (no protected player check)
    command = f"tempban {player} {duration} {reason}"
    result = await minecraft_server.send_command(command)

    if result.get("success"):
        return JSONResponse({
            "success": True,
            "message": f"Temporarily banned {player} for {duration}",
            "response": result.get("response", "")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to execute ban command")
        }, status_code=500)


@router.post("/api/minecraft/broadcast")
async def admin_broadcast_message(request: Request, user_info: dict = Depends(require_admin)):
    """
    Send a server-wide broadcast message (admin access).
    """
    body = await request.json()
    message = body.get("message", "").strip()
    admin_email = user_info.get("email", "unknown")

    if not message:
        return JSONResponse({"success": False, "error": "Message is required"}, status_code=400)

    if len(message) > 200:
        return JSONResponse({
            "success": False,
            "error": "Message too long. Maximum 200 characters allowed."
        }, status_code=400)

    # Sanitize message
    message = message.replace('\n', ' ').replace('\r', ' ')
    message = re.sub(r'[/\\@]', '', message)
    message = ' '.join(message.split())

    if not message:
        return JSONResponse({"success": False, "error": "Message is empty after sanitization"}, status_code=400)

    # Rate limit check
    current_time = time.time()
    last_broadcast = _admin_broadcast_cooldowns.get(admin_email, 0)
    if current_time - last_broadcast < BROADCAST_COOLDOWN_SECONDS:
        remaining = int(BROADCAST_COOLDOWN_SECONDS - (current_time - last_broadcast))
        return JSONResponse({
            "success": False,
            "error": f"Please wait {remaining} seconds before sending another broadcast."
        }, status_code=429)

    command = f'say [ADMIN] {message}'
    result = await minecraft_server.send_command(command)

    if result.get("success"):
        _admin_broadcast_cooldowns[admin_email] = current_time
        return JSONResponse({
            "success": True,
            "message": "Broadcast sent successfully",
            "response": result.get("response", "")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to send broadcast")
        }, status_code=500)


# Import warnings service
from app.services import warnings as warnings_service


@router.post("/api/minecraft/warn")
async def admin_warn_player(request: Request, user_info: dict = Depends(require_admin)):
    """
    Issue a warning to a player (admin access - no protected player filtering).
    """
    body = await request.json()
    player = extract_username(body.get("player", "").strip())
    reason = body.get("reason", "").strip()
    notify = body.get("notify", True)
    admin_email = user_info.get("email", "unknown")

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    if not reason:
        return JSONResponse({"success": False, "error": "Warning reason required"}, status_code=400)

    # Sanitize reason
    reason = reason[:200]
    reason = reason.replace('\n', ' ').replace('\r', ' ')
    reason = ' '.join(reason.split())

    # Admin can warn any player (no protected player check)
    warning = warnings_service.issue_warning(player, reason, admin_email)
    warning_count = warnings_service.get_warning_count(player)
    escalation = warnings_service.get_escalation_recommendation(player)

    # Notify player in-game if requested
    notified = False
    if notify:
        notify_command = f'msg {player} [WARNING] You have been warned: {reason[:100]}'
        result = await minecraft_server.send_command(notify_command)
        if result.get("success"):
            warnings_service.mark_warning_notified(warning.id)
            notified = True

    response_data = {
        "success": True,
        "message": f"Warning issued to {player}",
        "warning": {
            "id": warning.id,
            "player": warning.player,
            "reason": warning.reason,
            "timestamp": warning.timestamp,
            "notified": notified
        },
        "total_warnings": warning_count
    }

    if escalation:
        response_data["escalation_recommendation"] = escalation

    return JSONResponse(response_data)


@router.get("/api/minecraft/warnings")
async def admin_get_all_warnings(
    limit: int = Query(default=50, le=100, ge=1),
    user_info: dict = Depends(require_admin)
):
    """Get all recent warnings (admin access)."""
    warnings = warnings_service.get_all_warnings(limit=limit)

    return JSONResponse({
        "status": "ok",
        "count": len(warnings),
        "warnings": [
            {
                "id": w.id,
                "player": w.player,
                "reason": w.reason,
                "issued_by": w.issued_by,
                "timestamp": w.timestamp,
                "notified": w.notified
            }
            for w in warnings
        ]
    })


@router.get("/api/minecraft/warnings/{player}")
async def admin_get_player_warnings(player: str, user_info: dict = Depends(require_admin)):
    """Get warning history for a specific player (admin access)."""
    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    warnings = warnings_service.get_player_warnings(player)
    escalation = warnings_service.get_escalation_recommendation(player)

    response_data = {
        "status": "ok",
        "player": player,
        "count": len(warnings),
        "warnings": [
            {
                "id": w.id,
                "reason": w.reason,
                "issued_by": w.issued_by,
                "timestamp": w.timestamp,
                "notified": w.notified
            }
            for w in warnings
        ]
    }

    if escalation:
        response_data["escalation_recommendation"] = escalation

    return JSONResponse(response_data)


@router.delete("/api/minecraft/warnings/{warning_id}")
async def admin_delete_warning(warning_id: str, user_info: dict = Depends(require_admin)):
    """Delete a warning by ID (admin access - can delete any warning)."""
    admin_email = user_info.get("email", "unknown")

    warning = warnings_service.get_warning_by_id(warning_id)
    if not warning:
        return JSONResponse({
            "success": False,
            "error": "Warning not found"
        }, status_code=404)

    # Admin can delete any warning
    if warnings_service.delete_warning(warning_id, admin_email):
        return JSONResponse({
            "success": True,
            "message": f"Warning {warning_id} deleted"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to delete warning"
        }, status_code=500)


# =============================================================================
# Admin Server Logs (Less restrictive than staff)
# =============================================================================

@router.get("/api/minecraft/server-logs")
async def get_admin_server_logs(
    lines: int = Query(default=200, le=500, ge=10),
    search: Optional[str] = Query(default=None, max_length=50),
    user_info: dict = Depends(require_admin)
):
    """
    Get server logs for admin (less restrictive filtering than staff).
    """
    all_logs = minecraft_server.get_recent_logs(lines=500, filtered=True)

    if not all_logs:
        all_logs = minecraft_server.read_latest_log(lines=500)

    # Admin logs: only mask IPs, don't filter protected players or admin commands
    filtered_logs = []
    for log in all_logs:
        message = log.get("message", "")
        # Mask IP addresses
        masked_message = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP]', message)
        filtered_logs.append({
            "time": log.get("time", ""),
            "message": masked_message
        })

    # Optional search filter
    if search:
        search_lower = search.lower()
        if re.match(r'^[a-zA-Z0-9_]{1,16}$', search):
            filtered_logs = [
                log for log in filtered_logs
                if search_lower in log.get("message", "").lower()
            ]

    result_logs = filtered_logs[-lines:]

    return JSONResponse({
        "status": "ok",
        "count": len(result_logs),
        "logs": result_logs
    })


# =============================================================================
# Admin Whitelist Management
# =============================================================================

@router.get("/api/minecraft/whitelist")
async def admin_get_whitelist(user_info: dict = Depends(require_admin)):
    """Get current server whitelist (admin access)."""
    result = await minecraft_server.send_command("whitelist list")

    if not result.get("success"):
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to get whitelist")
        }, status_code=500)

    response = result.get("response", "")
    players = []
    if ":" in response:
        players_part = response.split(":")[-1].strip()
        if players_part:
            players = [p.strip() for p in players_part.split(",") if p.strip()]

    return JSONResponse({
        "status": "ok",
        "players": players,
        "count": len(players),
        "raw_response": response
    })


@router.post("/api/minecraft/whitelist/add")
async def admin_whitelist_add(request: Request, user_info: dict = Depends(require_admin)):
    """Add a player to the whitelist (admin access)."""
    body = await request.json()
    player = body.get("player", "").strip()

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    result = await minecraft_server.send_command(f"whitelist add {player}")

    if result.get("success"):
        return JSONResponse({
            "success": True,
            "message": f"Added {player} to whitelist",
            "response": result.get("response", "")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to add to whitelist")
        }, status_code=500)


@router.post("/api/minecraft/whitelist/remove")
async def admin_whitelist_remove(request: Request, user_info: dict = Depends(require_admin)):
    """Remove a player from the whitelist (admin access - no protected player check)."""
    body = await request.json()
    player = extract_username(body.get("player", "").strip())

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    # Admin can remove any player (no protected player check)
    result = await minecraft_server.send_command(f"whitelist remove {player}")

    if result.get("success"):
        return JSONResponse({
            "success": True,
            "message": f"Removed {player} from whitelist",
            "response": result.get("response", "")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to remove from whitelist")
        }, status_code=500)


# =============================================================================
# Admin CoreProtect Lookup
# =============================================================================

from app.services import coreprotect
from app.services import watchlist as watchlist_service
from app.services import player_notes as notes_service
from app.services import spectator_session as spectator_service
from app.services import investigation as investigation_service


@router.get("/api/minecraft/coreprotect/lookup")
async def admin_coreprotect_lookup(
    player: Optional[str] = Query(default=None, max_length=16),
    x: Optional[int] = Query(default=None),
    y: Optional[int] = Query(default=None),
    z: Optional[int] = Query(default=None),
    radius: int = Query(default=5, le=10, ge=1),
    limit: int = Query(default=50, le=100, ge=1),
    user_info: dict = Depends(require_admin)
):
    """
    Query CoreProtect database for block changes (admin access).
    """
    if not coreprotect.is_database_available():
        return JSONResponse({
            "success": False,
            "error": "CoreProtect database not available"
        }, status_code=503)

    if not player and (x is None or y is None or z is None):
        return JSONResponse({
            "success": False,
            "error": "Provide either 'player' or 'x', 'y', 'z' coordinates"
        }, status_code=400)

    results = []

    if player:
        if not PLAYER_NAME_PATTERN.match(player):
            return JSONResponse({
                "success": False,
                "error": "Invalid player name format"
            }, status_code=400)
        results = coreprotect.lookup_by_player(player, limit=limit)
    elif x is not None and y is not None and z is not None:
        results = coreprotect.lookup_by_coordinates(x, y, z, radius=radius, limit=limit)

    results_data = [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "player": r.player,
            "action": r.action,
            "world": r.world,
            "x": r.x,
            "y": r.y,
            "z": r.z,
            "block": r.block_type,
        }
        for r in results
    ]

    return JSONResponse({
        "status": "ok",
        "count": len(results_data),
        "results": results_data
    })


# =============================================================================
# Watchlist Management (Admin Only)
# =============================================================================

@router.get("/api/watchlist/valid-tags")
async def admin_get_valid_tags(user_info: dict = Depends(require_admin)):
    """Get list of valid watchlist tags."""
    return JSONResponse({
        "status": "ok",
        "tags": sorted(list(watchlist_service.VALID_TAGS))
    })


@router.get("/api/watchlist")
async def admin_get_watchlist(
    include_resolved: bool = Query(default=False),
    user_info: dict = Depends(require_admin)
):
    """Get all watchlist entries (admin access)."""
    entries = watchlist_service.get_watchlist(include_resolved=include_resolved)
    stats = watchlist_service.get_watchlist_stats()

    return JSONResponse({
        "status": "ok",
        "count": len(entries),
        "stats": stats,
        "entries": [
            {
                "id": e.id,
                "player": e.player,
                "level": e.level,
                "reason": e.reason,
                "evidence_notes": e.evidence_notes,
                "added_by": e.added_by,
                "added_at": e.added_at,
                "status": e.status,
                "tags": e.tags,
                "updated_at": e.updated_at,
                "updated_by": e.updated_by,
                "resolved_at": e.resolved_at,
                "resolved_by": e.resolved_by,
                "resolution_notes": e.resolution_notes
            }
            for e in entries
        ]
    })


@router.post("/api/watchlist")
async def admin_add_to_watchlist(request: Request, user_info: dict = Depends(require_admin)):
    """Add a player to the watchlist (admin only)."""
    body = await request.json()
    player = body.get("player", "").strip()
    level = body.get("level", "suspicious")
    reason = body.get("reason", "").strip()
    evidence_notes = body.get("evidence_notes", "").strip()
    tags = body.get("tags", [])
    admin_email = user_info.get("email", "unknown")

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name. Use 3-16 alphanumeric characters or underscores."
        }, status_code=400)

    if not reason:
        return JSONResponse({"success": False, "error": "Reason required"}, status_code=400)

    if level not in watchlist_service.WATCHLIST_LEVELS:
        return JSONResponse({
            "success": False,
            "error": f"Invalid level. Allowed: {', '.join(watchlist_service.WATCHLIST_LEVELS)}"
        }, status_code=400)

    # Check if protected
    if watchlist_service.is_protected_player(player):
        return JSONResponse({
            "success": False,
            "error": "Cannot add protected player to watchlist"
        }, status_code=403)

    entry = watchlist_service.add_to_watchlist(
        player=player,
        level=level,
        reason=reason,
        evidence_notes=evidence_notes,
        admin_email=admin_email,
        tags=tags
    )

    if entry:
        return JSONResponse({
            "success": True,
            "message": f"Added {player} to watchlist",
            "entry": {
                "id": entry.id,
                "player": entry.player,
                "level": entry.level,
                "status": entry.status
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to add to watchlist. Player may already be on active watchlist."
        }, status_code=400)


@router.put("/api/watchlist/{entry_id}")
async def admin_update_watchlist_entry(
    entry_id: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Update a watchlist entry (admin only)."""
    body = await request.json()
    admin_email = user_info.get("email", "unknown")

    entry = watchlist_service.update_watchlist_entry(
        entry_id=entry_id,
        admin_email=admin_email,
        level=body.get("level"),
        reason=body.get("reason"),
        evidence_notes=body.get("evidence_notes"),
        tags=body.get("tags")
    )

    if entry:
        return JSONResponse({
            "success": True,
            "message": "Watchlist entry updated",
            "entry": {
                "id": entry.id,
                "player": entry.player,
                "level": entry.level,
                "status": entry.status,
                "updated_at": entry.updated_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Entry not found or invalid update data"
        }, status_code=404)


@router.delete("/api/watchlist/{entry_id}")
async def admin_delete_watchlist_entry(entry_id: str, user_info: dict = Depends(require_admin)):
    """Delete a watchlist entry permanently (admin only)."""
    admin_email = user_info.get("email", "unknown")

    if watchlist_service.delete_watchlist_entry(entry_id, admin_email):
        return JSONResponse({
            "success": True,
            "message": f"Watchlist entry {entry_id} deleted"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Entry not found"
        }, status_code=404)


@router.post("/api/watchlist/{entry_id}/resolve")
async def admin_resolve_watchlist_entry(
    entry_id: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Resolve a watchlist entry (admin only)."""
    body = await request.json()
    resolution = body.get("resolution", "resolved")
    notes = body.get("notes", "")
    admin_email = user_info.get("email", "unknown")

    if resolution not in ["resolved", "false-positive"]:
        return JSONResponse({
            "success": False,
            "error": "Invalid resolution. Use 'resolved' or 'false-positive'"
        }, status_code=400)

    entry = watchlist_service.resolve_watchlist_entry(
        entry_id=entry_id,
        admin_email=admin_email,
        resolution=resolution,
        notes=notes
    )

    if entry:
        return JSONResponse({
            "success": True,
            "message": f"Entry marked as {resolution}",
            "entry": {
                "id": entry.id,
                "player": entry.player,
                "status": entry.status,
                "resolved_at": entry.resolved_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Entry not found"
        }, status_code=404)


# =============================================================================
# Player Notes (Admin can view all and delete any)
# =============================================================================

@router.get("/api/notes/{player}")
async def admin_get_player_notes(player: str, user_info: dict = Depends(require_admin)):
    """Get all notes for a player (admin access)."""
    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    notes = notes_service.get_player_notes(player)

    return JSONResponse({
        "status": "ok",
        "player": player,
        "count": len(notes),
        "notes": [
            {
                "id": n.id,
                "player": n.player,
                "content": n.content,
                "author": n.author,
                "author_name": n.author_name,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
                "category": n.category
            }
            for n in notes
        ]
    })


@router.post("/api/notes")
async def admin_add_note(request: Request, user_info: dict = Depends(require_admin)):
    """Add a note about a player (admin access)."""
    body = await request.json()
    player = body.get("player", "").strip()
    content = body.get("content", "").strip()
    category = body.get("category", "general")
    author_email = user_info.get("email", "unknown")
    author_name = user_info.get("name", author_email)

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not PLAYER_NAME_PATTERN.match(player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    if not content:
        return JSONResponse({"success": False, "error": "Note content required"}, status_code=400)

    note = notes_service.add_note(
        player=player,
        content=content,
        author_email=author_email,
        author_name=author_name,
        category=category
    )

    if note:
        return JSONResponse({
            "success": True,
            "message": "Note added",
            "note": {
                "id": note.id,
                "player": note.player,
                "category": note.category,
                "created_at": note.created_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to add note"
        }, status_code=500)


@router.put("/api/notes/{note_id}")
async def admin_update_note(note_id: str, request: Request, user_info: dict = Depends(require_admin)):
    """Update a note (admin can only edit own notes)."""
    body = await request.json()
    author_email = user_info.get("email", "unknown")

    note = notes_service.update_note(
        note_id=note_id,
        author_email=author_email,
        content=body.get("content"),
        category=body.get("category")
    )

    if note:
        return JSONResponse({
            "success": True,
            "message": "Note updated",
            "note": {
                "id": note.id,
                "updated_at": note.updated_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Note not found or you are not the author"
        }, status_code=404)


@router.delete("/api/notes/{note_id}")
async def admin_delete_note(note_id: str, user_info: dict = Depends(require_admin)):
    """Delete a note (admin can delete any note)."""
    author_email = user_info.get("email", "unknown")

    if notes_service.delete_note(note_id, author_email, is_admin=True):
        return JSONResponse({
            "success": True,
            "message": f"Note {note_id} deleted"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Note not found"
        }, status_code=404)


# =============================================================================
# Investigation Commands (Admin - Direct Access)
# =============================================================================

@router.get("/api/investigation/grimac/{player}")
async def admin_run_grimac(player: str, user_info: dict = Depends(require_admin)):
    """
    Get GrimAC violation history for a player from the database (admin access - no watchlist restriction).
    """
    from app.services import grimac as grimac_service
    
    admin_email = user_info.get("email", "unknown")

    # Validate player name
    if not re.match(r'^[a-zA-Z0-9_]{3,16}$', player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    # Query the GrimAC database directly - get more records
    result = grimac_service.get_player_violations(player, limit=100)

    if result.get('success'):
        # Format response for display
        summary = result.get('summary', {})
        violations = result.get('violations', [])
        
        if summary.get('total_count', 0) == 0:
            formatted_response = f"No violations found for {player}"
            if result.get('note'):
                formatted_response += f"\n({result.get('note')})"
        else:
            lines = [
                f"╔══════════════════════════════════════════════════════════════╗",
                f"║  GrimAC History: {player:<43} ║",
                f"╠══════════════════════════════════════════════════════════════╣",
                f"║  Total Violations: {summary.get('total_count', 0):<8} | Showing: {summary.get('showing', 0):<8} | Checks: {summary.get('unique_checks', 0):<3} ║",
                f"╚══════════════════════════════════════════════════════════════╝",
                "",
                "[ Check Breakdown ]"
            ]
            for check, count in sorted(summary.get('checks_breakdown', {}).items(), key=lambda x: -x[1]):
                bar = '█' * min(count, 20)
                lines.append(f"  {check:<15} {count:>4}  {bar}")
            
            lines.append("")
            lines.append("[ Violations by Date ]")
            
            # Group violations by date
            from collections import defaultdict
            by_date = defaultdict(list)
            for v in violations:
                date_part = v['created_at'].split(' ')[0]
                by_date[date_part].append(v)
            
            # Show all grouped by date
            for date in sorted(by_date.keys(), reverse=True):
                day_violations = by_date[date]
                lines.append(f"")
                lines.append(f"─── {date} ({len(day_violations)} violations) ───")
                for v in day_violations:
                    time_part = v['created_at'].split(' ')[1]
                    verbose = v['verbose'][:40] + '...' if len(v['verbose']) > 40 else v['verbose']
                    lines.append(f"  {time_part} │ {v['check_name']:<12} VL:{v['violation_level']:<3} │ {verbose}")
            
            if summary.get('total_count', 0) > summary.get('showing', 0):
                lines.append("")
                lines.append(f"⚠️  Showing {summary.get('showing')} of {summary.get('total_count')} total violations")
            
            formatted_response = "\n".join(lines)
        
        return JSONResponse({
            "success": True,
            "response": formatted_response,
            "data": result
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get('error', 'Unknown error')
        })


@router.get("/api/investigation/mtrack/{player}")
async def admin_run_mtrack(player: str, user_info: dict = Depends(require_admin)):
    """
    Run mtrack check command for a player (admin access - no watchlist restriction).
    """
    admin_email = user_info.get("email", "unknown")

    # Validate player name
    if not re.match(r'^[a-zA-Z0-9_]{3,16}$', player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    # Run the command directly (admin has no restrictions)
    result = await minecraft_server.send_command(f"mtrack check {player}")

    return JSONResponse({
        "success": result.get("success", False),
        "response": result.get("response", ""),
        "error": result.get("error")
    })


@router.post("/api/spectator/request")
async def admin_create_spectator_request(request: Request, user_info: dict = Depends(require_admin)):
    """Admin creates a spectator request (auto-approved)."""
    body = await request.json()
    player = body.get("player", "").strip()
    reason = body.get("reason", "Admin investigation").strip()
    duration = body.get("duration_minutes", 30)
    admin_email = user_info.get("email", "unknown")

    if not player:
        return JSONResponse({"success": False, "error": "Player name required"}, status_code=400)

    if not re.match(r'^[a-zA-Z0-9_]{3,16}$', player):
        return JSONResponse({
            "success": False,
            "error": "Invalid player name format"
        }, status_code=400)

    # Admin requests are auto-approved
    session = spectator_service.request_spectator(
        player=player,
        staff_email=admin_email,
        reason=reason,
        duration_minutes=duration,
        is_admin=True
    )

    if session:
        return JSONResponse({
            "success": True,
            "message": "Spectator session created (auto-approved)",
            "session": {
                "id": session.id,
                "player": session.player,
                "status": session.status
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to create spectator request"
        }, status_code=400)


# =============================================================================
# Spectator Session Management (Admin - Approval/Denial/Revoke)
# =============================================================================

@router.get("/api/spectator/pending")
async def admin_get_pending_spectator_requests(user_info: dict = Depends(require_admin)):
    """Get all pending spectator requests (admin only)."""
    requests = spectator_service.get_pending_requests()

    return JSONResponse({
        "status": "ok",
        "count": len(requests),
        "requests": [
            {
                "id": r.id,
                "player": r.player,
                "requested_by": r.requested_by,
                "requested_at": r.requested_at,
                "request_reason": r.request_reason,
                "watchlist_id": r.watchlist_id,
                "max_duration_minutes": r.max_duration_minutes
            }
            for r in requests
        ]
    })


@router.get("/api/spectator/active")
async def admin_get_active_spectator_sessions(user_info: dict = Depends(require_admin)):
    """Get all active spectator sessions (admin only)."""
    sessions = spectator_service.get_active_sessions()

    return JSONResponse({
        "status": "ok",
        "count": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "player": s.player,
                "requested_by": s.requested_by,
                "started_at": s.started_at,
                "max_duration_minutes": s.max_duration_minutes,
                "auto_approved": s.auto_approved
            }
            for s in sessions
        ]
    })


@router.get("/api/spectator/stats")
async def admin_get_spectator_stats(user_info: dict = Depends(require_admin)):
    """Get spectator session statistics (admin only)."""
    stats = spectator_service.get_spectator_stats()
    return JSONResponse({
        "status": "ok",
        "stats": stats
    })


@router.post("/api/spectator/{session_id}/approve")
async def admin_approve_spectator_request(
    session_id: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Approve a pending spectator request (admin only)."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    admin_email = user_info.get("email", "unknown")
    duration_override = body.get("duration_minutes")

    session = spectator_service.approve_request(
        session_id=session_id,
        admin_email=admin_email,
        duration_override=duration_override
    )

    if session:
        return JSONResponse({
            "success": True,
            "message": f"Spectator request approved for {session.player}",
            "session": {
                "id": session.id,
                "player": session.player,
                "status": session.status,
                "approved_at": session.approved_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Request not found or not pending"
        }, status_code=404)


@router.post("/api/spectator/{session_id}/deny")
async def admin_deny_spectator_request(
    session_id: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Deny a pending spectator request (admin only)."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    admin_email = user_info.get("email", "unknown")
    reason = body.get("reason", "")

    session = spectator_service.deny_request(
        session_id=session_id,
        admin_email=admin_email,
        reason=reason
    )

    if session:
        return JSONResponse({
            "success": True,
            "message": f"Spectator request denied for {session.player}",
            "session": {
                "id": session.id,
                "player": session.player,
                "status": session.status
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Request not found or not pending"
        }, status_code=404)


@router.post("/api/spectator/{session_id}/revoke")
async def admin_revoke_spectator_session(session_id: str, user_info: dict = Depends(require_admin)):
    """Force-end any spectator session (admin only)."""
    admin_email = user_info.get("email", "unknown")

    result = await spectator_service.revoke_session(session_id, admin_email)

    if result.get("success"):
        return JSONResponse({
            "success": True,
            "message": result.get("message", "Session revoked")
        })
    else:
        return JSONResponse({
            "success": False,
            "error": result.get("error", "Failed to revoke session")
        }, status_code=400)


# =============================================================================
# Staff Settings Management (Admin Only)
# =============================================================================

from app.services import staff_settings as staff_settings_service
from app.core.config import STAFF_EMAILS


@router.get("/api/staff-settings")
async def admin_get_all_staff_settings(user_info: dict = Depends(require_admin)):
    """Get all staff settings (admin only)."""
    settings = staff_settings_service.get_all_staff_settings()
    available_features = staff_settings_service.get_available_features()

    # Include all staff emails even if they don't have custom settings
    staff_with_settings = {s.email for s in settings}
    all_staff = []

    for setting in settings:
        all_staff.append({
            "email": setting.email,
            "hidden_features": setting.hidden_features,
            "updated_at": setting.updated_at,
            "updated_by": setting.updated_by
        })

    # Add staff without custom settings
    for email in STAFF_EMAILS:
        if email.lower() not in staff_with_settings:
            all_staff.append({
                "email": email.lower(),
                "hidden_features": [],
                "updated_at": None,
                "updated_by": None
            })

    return JSONResponse({
        "status": "ok",
        "staff": all_staff,
        "available_features": available_features
    })


@router.get("/api/staff-settings/{staff_email}")
async def admin_get_staff_settings(staff_email: str, user_info: dict = Depends(require_admin)):
    """Get settings for a specific staff member (admin only)."""
    settings = staff_settings_service.get_staff_settings(staff_email)

    return JSONResponse({
        "status": "ok",
        "settings": {
            "email": settings.email,
            "hidden_features": settings.hidden_features,
            "updated_at": settings.updated_at,
            "updated_by": settings.updated_by
        }
    })


@router.put("/api/staff-settings/{staff_email}")
async def admin_update_staff_settings(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Update feature visibility for a staff member (admin only)."""
    body = await request.json()
    hidden_features = body.get("hidden_features", [])
    admin_email = user_info.get("email", "unknown")

    settings = staff_settings_service.update_staff_settings(
        staff_email=staff_email,
        hidden_features=hidden_features,
        admin_email=admin_email
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Settings updated for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features,
                "updated_at": settings.updated_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to update settings"
        }, status_code=500)


@router.post("/api/staff-settings/{staff_email}/toggle")
async def admin_toggle_staff_feature(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Toggle a single feature for a staff member (admin only)."""
    body = await request.json()
    feature = body.get("feature", "")
    visible = body.get("visible", True)
    admin_email = user_info.get("email", "unknown")

    if not feature:
        return JSONResponse({
            "success": False,
            "error": "Feature is required"
        }, status_code=400)

    settings = staff_settings_service.toggle_feature_for_staff(
        staff_email=staff_email,
        feature=feature,
        visible=visible,
        admin_email=admin_email
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Feature '{feature}' {'shown' if visible else 'hidden'} for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Invalid feature or failed to update"
        }, status_code=400)


@router.delete("/api/staff-settings/{staff_email}")
async def admin_delete_staff_settings(staff_email: str, user_info: dict = Depends(require_admin)):
    """Reset staff settings to defaults (admin only)."""
    if staff_settings_service.delete_staff_settings(staff_email):
        return JSONResponse({
            "success": True,
            "message": f"Settings reset for {staff_email}"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "No custom settings found"
        }, status_code=404)


# =============================================================================
# Whitelist Cache for Autocomplete
# =============================================================================

# Cache for whitelist (5 minute TTL)
_whitelist_cache = {"players": [], "last_fetch": 0}
WHITELIST_CACHE_TTL = 300  # 5 minutes


@router.get("/api/whitelist/autocomplete")
async def get_whitelist_autocomplete(user_info: dict = Depends(require_admin)):
    """Get whitelist for autocomplete (cached)."""
    import time

    current_time = time.time()

    # Check cache
    if current_time - _whitelist_cache["last_fetch"] < WHITELIST_CACHE_TTL and _whitelist_cache["players"]:
        return JSONResponse({
            "status": "ok",
            "players": _whitelist_cache["players"],
            "cached": True
        })

    # Fetch fresh whitelist
    result = await minecraft_server.send_command("whitelist list")

    if result.get("success"):
        response = result.get("response", "")
        players = []
        if ":" in response:
            players_part = response.split(":")[-1].strip()
            if players_part:
                players = [p.strip() for p in players_part.split(",") if p.strip()]

        # Update cache
        _whitelist_cache["players"] = sorted(players, key=str.lower)
        _whitelist_cache["last_fetch"] = current_time

        return JSONResponse({
            "status": "ok",
            "players": _whitelist_cache["players"],
            "cached": False
        })

    return JSONResponse({
        "status": "ok",
        "players": _whitelist_cache["players"],  # Return stale cache on error
        "cached": True
    })
