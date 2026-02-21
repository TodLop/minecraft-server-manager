# app/routers/admin_analytics.py
"""
Admin Analytics Sub-Router — Server performance monitoring dashboard.

Provides historical metrics API, live WebSocket stream, and the dashboard page.
Registered as a sub-router under admin.py (inherits /minecraft/admin prefix).
"""

import asyncio
import json as json_module
import logging
import os
import time
from base64 import b64decode

from fastapi import APIRouter, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import TimestampSigner

from app.core.config import TEMPLATES_DIR
from app.core.minecraft_access import require_minecraft_admin, is_minecraft_admin_email
from app.services import metrics_db
from app.services import server_metrics

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Time range presets (label → seconds)
RANGE_PRESETS = {
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(request: Request, user_info: dict = Depends(require_minecraft_admin)):
    """Render the server analytics dashboard page."""
    return templates.TemplateResponse("admin/analytics.html", {
        "request": request,
        "user_info": user_info,
        "is_admin": True,
    })


@router.get("/api/analytics/metrics")
async def get_analytics_metrics(
    range: str = "1h",
    user_info: dict = Depends(require_minecraft_admin),
):
    """Get historical CPU/RAM metrics for the requested time range."""
    range_sec = RANGE_PRESETS.get(range, 3600)
    end = time.time()
    start = end - range_sec

    metrics = metrics_db.query_metrics(start, end)

    return JSONResponse({
        "status": "ok",
        "range": range,
        "count": len(metrics),
        "metrics": metrics,
    })


@router.get("/api/analytics/disk")
async def get_analytics_disk(
    range: str = "30d",
    user_info: dict = Depends(require_minecraft_admin),
):
    """Get historical disk size data."""
    range_sec = RANGE_PRESETS.get(range, 30 * 24 * 3600)
    end = time.time()
    start = end - range_sec

    disk_data = metrics_db.query_disk_size(start, end)

    return JSONResponse({
        "status": "ok",
        "range": range,
        "count": len(disk_data),
        "disk": disk_data,
    })


@router.get("/api/analytics/current")
async def get_analytics_current(user_info: dict = Depends(require_minecraft_admin)):
    """Get the latest metric snapshot."""
    latest = metrics_db.get_latest_metric()
    disk = metrics_db.get_latest_disk_size()

    return JSONResponse({
        "status": "ok",
        "metric": latest,
        "disk_mb": disk,
    })


@router.websocket("/ws/minecraft/metrics")
async def websocket_metrics(websocket: WebSocket):
    """WebSocket endpoint for live metrics streaming (admin only)."""
    # WebSocket auth: manually parse session cookie (SessionMiddleware doesn't populate .session on WS)
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        await websocket.close(code=4003, reason="Server config error")
        return

    cookie_header = websocket.headers.get("cookie", "")
    session_cookie = None
    for cookie in cookie_header.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("session="):
            session_cookie = cookie[len("session="):]
            break

    if not session_cookie:
        await websocket.close(code=4003, reason="No session cookie")
        return

    try:
        signer = TimestampSigner(secret_key)
        data = signer.unsign(session_cookie.encode("utf-8"), max_age=14 * 24 * 60 * 60)
        session_data = json_module.loads(b64decode(data))
    except Exception:
        await websocket.close(code=4003, reason="Invalid session")
        return

    user_info = session_data.get("user_info")
    if not user_info or not is_minecraft_admin_email(user_info.get("email", "")):
        await websocket.close(code=4003, reason="Forbidden")
        return

    await websocket.accept()

    metric_queue: asyncio.Queue = asyncio.Queue()

    async def on_metric(data: dict):
        await metric_queue.put(data)

    server_metrics.subscribe_to_metrics(on_metric)

    try:
        while True:
            try:
                metric = await asyncio.wait_for(metric_queue.get(), timeout=30.0)
                await websocket.send_json(metric)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Metrics WebSocket error", exc_info=True)
    finally:
        server_metrics.unsubscribe_from_metrics(on_metric)
