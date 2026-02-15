"""Admin panel route aggregator for Minecraft management."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import require_admin
from app.core.config import APP_VERSION, TEMPLATES_DIR
from app.services import minecraft_server, minecraft_updater
from app.services.modrinth_api import batch_get_icons

from app.routers.admin_moderation import router as moderation_router
from app.routers.admin_rbac import router as rbac_router
from app.routers.admin_scheduler import router as scheduler_router
from app.routers.admin_server import router as server_router

router = APIRouter(prefix="/minecraft/admin", tags=["Admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router.include_router(server_router)
router.include_router(scheduler_router)
router.include_router(moderation_router)
router.include_router(rbac_router)


@router.get("/api/overview")
async def get_admin_overview(user_info: dict = Depends(require_admin)):
    """Get aggregated overview data for admin dashboard."""
    from app.services.reboot_scheduler import get_scheduler

    server_status = minecraft_server.get_server_status()
    versions_data = minecraft_updater.load_versions()
    scheduler = get_scheduler()
    scheduler_status = scheduler.get_status()

    active_services = 1
    if server_status.running:
        active_services += 1

    uptime_str = scheduler_status.get("uptime_formatted", "--")
    if not server_status.running:
        uptime_str = "Offline"

    return JSONResponse(
        {
            "status": "ok",
            "active_services": active_services,
            "pending_updates": versions_data.get("pending_updates", 0),
            "uptime": uptime_str,
            "last_check": versions_data.get("last_check"),
            "server_running": server_status.running,
            "players_online": server_status.players_online or 0,
            "app_version": APP_VERSION,
        }
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def minecraft_dashboard(request: Request, user_info: dict = Depends(require_admin)):
    """Minecraft server management dashboard."""
    versions_data = minecraft_updater.load_versions()
    file_status = minecraft_updater.get_server_status()
    server_status = minecraft_server.get_server_status()
    update_logs = minecraft_updater.get_update_logs(limit=10)

    tracked_plugins = versions_data.get("plugins", {})
    modrinth_ids = []
    for plugin_id, plugin_config in tracked_plugins.items():
        if plugin_config.get("source") == "modrinth" and plugin_config.get("project_id"):
            modrinth_ids.append(plugin_config["project_id"])

    plugin_icons = {}
    if modrinth_ids:
        plugin_icons = await batch_get_icons(modrinth_ids)

    return templates.TemplateResponse(
        "admin/minecraft.html",
        {
            "request": request,
            "user_info": user_info,
            "is_admin": True,
            "versions_data": versions_data,
            "server_status": {
                **file_status,
                "running": server_status.running,
                "pid": server_status.pid,
                "players_online": server_status.players_online,
                "max_players": server_status.max_players,
            },
            "update_logs": update_logs,
            "plugin_icons": plugin_icons,
        },
    )
