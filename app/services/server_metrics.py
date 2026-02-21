# app/services/server_metrics.py
"""
Minecraft Server Metrics Collector

Collects CPU%, RAM, disk size on scheduled intervals and broadcasts
live data to WebSocket subscribers.

Lifecycle: start_scheduler() / stop_scheduler() — called from app lifespan.
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Callable, List, Optional

import psutil

from app.core.config import MINECRAFT_SERVER_PATH
from app.services import minecraft_server
from app.services import metrics_db

logger = logging.getLogger(__name__)

# Collection intervals (seconds)
METRICS_INTERVAL = 3
TPS_INTERVAL = 10         # Paper /tps + /mspt polling
DISK_INTERVAL = 30 * 60   # 30 minutes
DOWNSAMPLE_INTERVAL = 3600  # 1 hour

# Paper /mspt first bucket (5s avg/min/max), supports optional icon and newlines.
_MSPT_5S_RE = re.compile(
    r'from last 5s,\s*10s,\s*1m:\s*(?:[^\d\s]\s*)?'
    r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)',
    flags=re.IGNORECASE,
)
_MSPT_TRIPLE_FALLBACK_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)'
)

# Latest TPS/MSPT values (updated by _tps_loop, consumed by _metrics_loop)
_latest_tps: Optional[float] = None
_latest_mspt: Optional[float] = None

# Subscriber list for live metric broadcasts
_metric_subscribers: List[Callable] = []


def subscribe_to_metrics(callback: Callable):
    _metric_subscribers.append(callback)


def unsubscribe_from_metrics(callback: Callable):
    if callback in _metric_subscribers:
        _metric_subscribers.remove(callback)


async def _broadcast_metric(data: dict):
    """Send metric to all subscribers (WebSocket handlers)."""
    for callback in list(_metric_subscribers):
        try:
            await callback(data)
        except Exception:
            logger.debug("Failed to broadcast to subscriber, removing")
            try:
                _metric_subscribers.remove(callback)
            except ValueError:
                pass


def _get_java_process() -> Optional[psutil.Process]:
    """Find the Minecraft server's Java process by PID from minecraft_server module."""
    status = minecraft_server.get_server_status()
    if not status.running or not status.pid:
        return None
    try:
        proc = psutil.Process(status.pid)
        if proc.is_running():
            return proc
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


# ─── Scheduler Tasks ──────────────────────────────────────────────

_metrics_task: Optional[asyncio.Task] = None
_tps_task: Optional[asyncio.Task] = None
_disk_task: Optional[asyncio.Task] = None
_downsample_task: Optional[asyncio.Task] = None


def _parse_tps(text: str) -> Optional[float]:
    """
    Parse Paper's /tps output for the 1m TPS value.

    Expected format:
        TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0
    """
    match = re.search(r'TPS from last 1m, 5m, 15m:\s*\*?([\d.]+)', text)
    if match:
        return float(match.group(1))
    return None


def _parse_mspt(text: str) -> Optional[float]:
    """
    Parse Paper's /mspt output for the avg MSPT from the 5s bucket.

    Expected format:
        Server tick times (avg/min/max) from last 5s, 10s, 1m:
        ◴ 11.6/6.6/18.8, 11.8/4.8/76.2, 12.0/4.8/88.8

    Returns the avg (first value) from the 5s bucket.
    """
    match = _MSPT_5S_RE.search(text)
    if not match:
        # Fallback for minor format drift while still extracting first avg/min/max triple.
        match = _MSPT_TRIPLE_FALLBACK_RE.search(text)
    if match:
        return float(match.group(1))
    return None


async def _metrics_loop():
    """Collect CPU% and RAM every METRICS_INTERVAL seconds."""
    proc: Optional[psutil.Process] = None
    prev_pid: Optional[int] = None

    while True:
        try:
            status = minecraft_server.get_server_status()

            if not status.running or not status.pid:
                proc = None
                prev_pid = None
                await asyncio.sleep(METRICS_INTERVAL)
                continue

            # Re-acquire process handle if PID changed (server restarted)
            if status.pid != prev_pid:
                try:
                    proc = psutil.Process(status.pid)
                    # Prime the cpu_percent counter (first call always returns 0)
                    proc.cpu_percent(interval=None)
                    prev_pid = status.pid
                    await asyncio.sleep(METRICS_INTERVAL)
                    continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc = None
                    prev_pid = None
                    await asyncio.sleep(METRICS_INTERVAL)
                    continue

            if proc is None:
                await asyncio.sleep(METRICS_INTERVAL)
                continue

            try:
                cpu = proc.cpu_percent(interval=None)
                mem_info = proc.memory_info()
                ram_mb = mem_info.rss / (1024 * 1024)
                players = status.players_online or 0

                # Store in DB (include latest TPS/MSPT if available)
                metrics_db.insert_raw_metric(cpu, ram_mb, players,
                                             tps=_latest_tps, mspt=_latest_mspt)

                # Broadcast to WebSocket subscribers
                metric_data = {
                    "type": "metric",
                    "timestamp": time.time(),
                    "cpu_percent": round(cpu, 1),
                    "ram_mb": round(ram_mb, 1),
                    "players": players,
                    "tps": round(_latest_tps, 2) if _latest_tps is not None else None,
                    "mspt": round(_latest_mspt, 2) if _latest_mspt is not None else None,
                }
                await _broadcast_metric(metric_data)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = None
                prev_pid = None

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Error in metrics collection loop", exc_info=True)

        await asyncio.sleep(METRICS_INTERVAL)


async def _tps_loop():
    """Collect TPS/MSPT from Paper's built-in commands via RCON."""
    global _latest_tps, _latest_mspt

    while True:
        try:
            status = minecraft_server.get_server_status()
            if status.running:
                # TPS
                tps_result = await minecraft_server.send_command("tps")
                if tps_result.get("success"):
                    tps = _parse_tps(tps_result["response"])
                    if tps is not None:
                        _latest_tps = tps
                    else:
                        logger.warning("Failed to parse TPS from: %s", tps_result["response"])
                else:
                    _latest_tps = None

                # MSPT
                mspt_result = await minecraft_server.send_command("mspt")
                if mspt_result.get("success"):
                    mspt = _parse_mspt(mspt_result["response"])
                    if mspt is not None:
                        _latest_mspt = mspt
                    else:
                        logger.warning("Failed to parse MSPT from: %s", mspt_result["response"])
                else:
                    _latest_mspt = None
            else:
                _latest_tps = None
                _latest_mspt = None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Error in TPS collection loop", exc_info=True)
            _latest_tps = None
            _latest_mspt = None

        await asyncio.sleep(TPS_INTERVAL)


async def _disk_loop():
    """Measure Minecraft server directory size every DISK_INTERVAL."""
    while True:
        try:
            server_path = MINECRAFT_SERVER_PATH
            if server_path.exists():
                # Run in thread to avoid blocking the event loop
                total_bytes = await asyncio.to_thread(_calculate_dir_size, server_path)
                size_mb = total_bytes / (1024 * 1024)
                metrics_db.insert_disk_size(size_mb)
                logger.debug("Disk size recorded: %.1f MB", size_mb)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Error in disk size collection", exc_info=True)

        await asyncio.sleep(DISK_INTERVAL)


def _calculate_dir_size(path: Path) -> int:
    """Calculate total size of a directory (runs in thread)."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


async def _downsample_loop():
    """Run downsampling every DOWNSAMPLE_INTERVAL."""
    while True:
        await asyncio.sleep(DOWNSAMPLE_INTERVAL)
        try:
            await asyncio.to_thread(metrics_db.downsample)
            logger.debug("Metrics downsampling completed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Error in downsample loop", exc_info=True)


# ─── Lifecycle ────────────────────────────────────────────────────

async def start_scheduler():
    """Start all metrics collection tasks."""
    global _metrics_task, _tps_task, _disk_task, _downsample_task

    # Initialize the database
    metrics_db.init_db()

    _metrics_task = asyncio.create_task(_metrics_loop())
    _tps_task = asyncio.create_task(_tps_loop())
    _disk_task = asyncio.create_task(_disk_loop())
    _downsample_task = asyncio.create_task(_downsample_loop())

    logger.info("Server metrics collector started")


async def stop_scheduler():
    """Stop all metrics collection tasks."""
    global _metrics_task, _tps_task, _disk_task, _downsample_task

    for task, name in [(_metrics_task, "metrics"), (_tps_task, "tps"), (_disk_task, "disk"), (_downsample_task, "downsample")]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _metrics_task = None
    _tps_task = None
    _disk_task = None
    _downsample_task = None

    logger.info("Server metrics collector stopped")
