# app/services/minecraft_server.py
"""
Minecraft Server Process Management Service

Handles:
- Starting/stopping/restarting the server
- Process status monitoring
- Log streaming
- Command execution (RCON or stdin)
- Graceful shutdown
"""

import asyncio
import json
import logging
import os
import re
import signal
import socket
import subprocess
import time
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List
from collections import deque

from app.core.config import MINECRAFT_SERVER_PATH
from app.services.rcon import (
    RCONClient, RCONConfig, get_rcon_config, load_server_properties,
    strip_minecraft_colors,
)

logger = logging.getLogger(__name__)

# Export an alias for external modules (admin.py uses minecraft_server.SERVER_DIR)
SERVER_DIR = MINECRAFT_SERVER_PATH

# Configuration (paths derived from central config)
SERVER_PROPERTIES = MINECRAFT_SERVER_PATH / "server.properties"
START_SCRIPT = MINECRAFT_SERVER_PATH / "start.sh"
LOGS_DIR = MINECRAFT_SERVER_PATH / "logs"
LATEST_LOG = LOGS_DIR / "latest.log"
CONSOLE_HISTORY_FILE = LOGS_DIR / "cora_console_history.jsonl"
PID_FILE = MINECRAFT_SERVER_PATH / "server.pid"

# Log messages to filter out (noise)
LOG_FILTER_PATTERNS = [
    "Thread RCON Client",
    "Rcon issued server command: /list",
]

# Status cache TTL
STATUS_CACHE_TTL = 5.0
DEFAULT_READY_TIMEOUT_SEC = 120
READY_POLL_INTERVAL_SEC = 1.0
PROCESS_BOOT_GRACE_SEC = 20
RESTART_START_RETRIES = 2
RESTART_RETRY_DELAY_SEC = 3
RESTART_COOLDOWN_SECONDS = 120


@dataclass
class ServerStatus:
    """Server status information"""
    running: bool = False
    process_running: bool = False
    game_port_listening: bool = False
    rcon_port_listening: bool = False
    healthy: bool = False
    state_reason: str = "stopped"
    pid: Optional[int] = None
    uptime_seconds: Optional[int] = None
    started_at: Optional[str] = None
    players_online: int = 0
    max_players: int = 20
    version: Optional[str] = None
    memory_used: Optional[str] = None


class ServerManager:
    """Encapsulates all mutable server state (replaces module-level globals)."""

    def __init__(self):
        self.log_buffer: deque = deque(maxlen=500)
        self.log_subscribers: List[Callable] = []
        self.process_lock = asyncio.Lock()
        self.restart_guard_lock = asyncio.Lock()
        self.log_reader_task: Optional[asyncio.Task] = None
        self.last_log_position: int = 0
        self.last_log_inode: Optional[int] = None

        # Status cache
        self.status_cache: Optional[dict] = None
        self.status_cache_time: float = 0
        self.status_refreshing: bool = False

        # Deduplication
        self.last_message: str = ""
        self.last_message_time: float = 0.0

        # Restart deduplication guard
        self.restart_in_progress: bool = False
        self.last_restart_completed_at: Optional[datetime] = None
        self.last_restart_source: str = ""

    def _restart_cooldown_remaining_seconds(self, now: datetime) -> int:
        if self.last_restart_completed_at is None:
            return 0
        elapsed = (now - self.last_restart_completed_at).total_seconds()
        remaining = RESTART_COOLDOWN_SECONDS - elapsed
        return max(0, int(math.ceil(remaining)))

    # ------------------------------------------------------------------
    # Log filtering & persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _should_filter_log(message: str) -> bool:
        for pattern in LOG_FILTER_PATTERNS:
            if pattern in message:
                return True
        return False

    def _save_console_history(self):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONSOLE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                for entry in self.log_buffer:
                    f.write(json.dumps(entry) + '\n')
            logger.info(f"Saved {len(self.log_buffer)} log entries to {CONSOLE_HISTORY_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to save console history: {e}")
            return False

    def _load_console_history(self):
        if not CONSOLE_HISTORY_FILE.exists():
            logger.info("No console history file found, starting fresh")
            return False
        try:
            loaded_count = 0
            with open(CONSOLE_HISTORY_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self.log_buffer.append(entry)
                        loaded_count += 1
                    except json.JSONDecodeError:
                        continue
            logger.info(f"Loaded {loaded_count} log entries from history")
            return True
        except Exception as e:
            logger.error(f"Failed to load console history: {e}")
            return False

    # ------------------------------------------------------------------
    # Process detection (sync — called via asyncio.to_thread when needed)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_pid_file() -> Optional[int]:
        if PID_FILE.exists():
            try:
                return int(PID_FILE.read_text().strip())
            except (ValueError, IOError):
                pass
        return None

    @staticmethod
    def _write_pid_file(pid: int) -> None:
        PID_FILE.write_text(str(pid))

    @staticmethod
    def _delete_pid_file() -> None:
        if PID_FILE.exists():
            PID_FILE.unlink()

    @staticmethod
    def _is_minecraft_process(pid: int) -> bool:
        """Check if a process with given PID is actually the Minecraft server"""
        try:
            os.kill(pid, 0)
        except OSError:
            return False

        try:
            if Path(f"/proc/{pid}/cmdline").exists():
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    cmdline = f.read()
                    return "java" in cmdline.lower() and "paper" in cmdline.lower()
            else:
                result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    cmdline = result.stdout.lower()
                    return "java" in cmdline and "paper" in cmdline
        except Exception as e:
            logger.error(f"Error checking process {pid}: {e}")

        return False

    @staticmethod
    def _find_minecraft_pid() -> Optional[int]:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "java.*paper.*\\.jar"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split()[0])
        except Exception:
            pass
        return None

    @staticmethod
    def _get_process_start_time(pid: int) -> Optional[datetime]:
        """Get the actual start time of a process from the OS.

        Uses ``ps -o lstart=`` which returns a string like
        ``Wed Feb 19 19:25:17 2026``.  This is independent of the Python
        app lifecycle, so run.py restarts don't affect the value.
        """
        try:
            result = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # macOS format: "Wed Feb 19 19:25:17 2026"
                raw = result.stdout.strip()
                return datetime.strptime(raw, "%a %b %d %H:%M:%S %Y")
        except Exception as e:
            logger.warning(f"Failed to get process start time for PID {pid}: {e}")
        return None

    def _get_process_snapshot_sync(self) -> tuple[bool, Optional[int], bool]:
        """
        Return process snapshot as (process_running, pid, stale_pid_detected).
        Also heals stale PID files when detected.
        """
        pid = self._read_pid_file()
        if pid and self._is_minecraft_process(pid):
            return True, pid, False

        stale_pid_detected = False
        if pid:
            stale_pid_detected = True
            logger.warning(f"Stale PID file detected (PID {pid} is not Minecraft), cleaning up")
            self._delete_pid_file()

        found_pid = self._find_minecraft_pid()
        if found_pid:
            if pid != found_pid:
                logger.info(f"Found Minecraft process via pgrep: PID {found_pid}")
            self._write_pid_file(found_pid)
            return True, found_pid, stale_pid_detected

        return False, None, stale_pid_detected

    @staticmethod
    def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
        """Check whether a local TCP port accepts connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                return sock.connect_ex((host, int(port))) == 0
        except OSError:
            return False

    def _is_server_running_sync(self) -> bool:
        """Sync version — shells out to ps/pgrep. Use is_server_running() for async."""
        running, _, _ = self._get_process_snapshot_sync()
        return running

    def _get_server_pid_sync(self) -> Optional[int]:
        _, pid, _ = self._get_process_snapshot_sync()
        return pid

    # ------------------------------------------------------------------
    # Async wrappers (run blocking I/O in thread pool)
    # ------------------------------------------------------------------

    async def is_server_running_async(self) -> bool:
        return await asyncio.to_thread(self._is_server_running_sync)

    async def get_server_pid_async(self) -> Optional[int]:
        return await asyncio.to_thread(self._get_server_pid_sync)

    def _probe_rcon_ready_once(self) -> tuple[bool, str]:
        """Best-effort readiness check: RCON connect + simple command."""
        rcon_config = get_rcon_config()
        if not rcon_config.enabled or not rcon_config.password:
            return False, "rcon_not_configured"

        client = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
        try:
            if not client.connect():
                return False, "rcon_connect_failed"
            client.send_command("list")
            return True, "ready"
        except Exception as e:
            return False, f"rcon_error: {e}"
        finally:
            client.disconnect()

    async def _wait_for_server_ready(self, timeout_sec: int, require_rcon_ready: bool) -> dict:
        """Wait until the process is alive and (optionally) RCON responds."""
        timeout_sec = max(1, int(timeout_sec))
        deadline = time.monotonic() + timeout_sec
        started_at = time.monotonic()
        checks = {
            "process_alive": False,
            "rcon_ready": False,
            "last_rcon_error": None,
            "elapsed_seconds": 0,
            "timeout_seconds": timeout_sec,
        }

        while time.monotonic() < deadline:
            if not self._is_server_running_sync():
                elapsed = time.monotonic() - started_at
                checks["elapsed_seconds"] = int(elapsed)
                if elapsed < PROCESS_BOOT_GRACE_SEC:
                    await asyncio.sleep(READY_POLL_INTERVAL_SEC)
                    continue
                self._delete_pid_file()
                return {
                    "success": False,
                    "error_code": "process_exited_early",
                    "error": "Server process exited before readiness checks completed",
                    "ready_checks": checks,
                }

            checks["process_alive"] = True
            checks["elapsed_seconds"] = int(time.monotonic() - started_at)

            if not require_rcon_ready:
                return {"success": True, "ready_checks": checks}

            rcon_ready, rcon_status = await asyncio.to_thread(self._probe_rcon_ready_once)
            if rcon_ready:
                checks["rcon_ready"] = True
                checks["last_rcon_error"] = None
                return {"success": True, "ready_checks": checks}

            checks["last_rcon_error"] = rcon_status
            await asyncio.sleep(READY_POLL_INTERVAL_SEC)

        checks["elapsed_seconds"] = int(time.monotonic() - started_at)
        return {
            "success": False,
            "error_code": "rcon_not_ready_timeout",
            "error": (
                f"Server started but did not become ready within {timeout_sec}s "
                f"(last_rcon_error={checks['last_rcon_error']})"
            ),
            "ready_checks": checks,
        }

    # ------------------------------------------------------------------
    # Server control
    # ------------------------------------------------------------------

    async def start_server(
        self,
        wait_for_ready: bool = False,
        ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
        require_rcon_ready: bool = True,
    ) -> dict:
        """Start the Minecraft server as a detached process"""
        async with self.process_lock:
            if self._is_server_running_sync():
                return {"success": False, "error": "Server is already running"}

            if not START_SCRIPT.exists():
                return {"success": False, "error": "start.sh not found"}

            try:
                # Cancel existing log tailer if any
                if self.log_reader_task and not self.log_reader_task.done():
                    self.log_reader_task.cancel()
                    try:
                        await asyncio.wait_for(self.log_reader_task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

                self.log_buffer.clear()

                # Start reading from CURRENT end of log file (skip old content)
                if LATEST_LOG.exists():
                    self.last_log_position = LATEST_LOG.stat().st_size
                    self.last_log_inode = LATEST_LOG.stat().st_ino
                else:
                    self.last_log_position = 0
                    self.last_log_inode = None

                separator_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": "[CORA] =============================================="
                }
                start_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": "[CORA] Starting Minecraft server..."
                }
                self.log_buffer.append(separator_entry)
                self.log_buffer.append(start_entry)

                for callback in self.log_subscribers:
                    try:
                        await callback(start_entry)
                    except Exception:
                        pass

                process = subprocess.Popen(
                    ["sh", str(START_SCRIPT)],
                    cwd=str(MINECRAFT_SERVER_PATH),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

                self._write_pid_file(process.pid)
                self.log_reader_task = asyncio.create_task(self._tail_log_file())

                result = {
                    "success": True,
                    "pid": process.pid,
                    "ready": False,
                    "message": "Server starting (detached mode)..."
                }

                if not wait_for_ready:
                    return result

                ready_result = await self._wait_for_server_ready(
                    timeout_sec=ready_timeout_sec,
                    require_rcon_ready=require_rcon_ready,
                )
                if not ready_result.get("success"):
                    return {
                        "success": False,
                        "pid": process.pid,
                        "ready": False,
                        "error": ready_result.get("error", "Server failed readiness checks"),
                        "error_code": ready_result.get("error_code"),
                        "ready_checks": ready_result.get("ready_checks"),
                    }

                result["ready"] = True
                result["message"] = "Server started and passed readiness checks"
                result["ready_checks"] = ready_result.get("ready_checks", {})
                return result

            except Exception as e:
                return {"success": False, "error": str(e)}

    async def _tail_log_file(self):
        """Background task to tail the server log file"""
        logger.info("Log file tailer started")
        self.last_message = ""
        self.last_message_time = 0.0

        try:
            while True:
                if not self._is_server_running_sync():
                    logger.info("Server stopped, tailer exiting")
                    stop_entry = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "message": "[CORA] Server process stopped"
                    }
                    self.log_buffer.append(stop_entry)
                    for callback in self.log_subscribers:
                        try:
                            await callback(stop_entry)
                        except Exception:
                            pass
                    break

                if LATEST_LOG.exists():
                    try:
                        current_inode = LATEST_LOG.stat().st_ino
                        current_size = LATEST_LOG.stat().st_size

                        if self.last_log_inode is not None and (
                            current_inode != self.last_log_inode or current_size < self.last_log_position
                        ):
                            logger.warning(
                                f"Log file rotated (inode: {self.last_log_inode} -> {current_inode}, "
                                f"size: {self.last_log_position} -> {current_size})"
                            )
                            self.last_log_position = 0
                            rotation_entry = {
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "message": "[CORA] Log file rotated - new server session"
                            }
                            self.log_buffer.append(rotation_entry)
                            for callback in self.log_subscribers:
                                try:
                                    await callback(rotation_entry)
                                except Exception:
                                    pass

                        self.last_log_inode = current_inode

                        with open(LATEST_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                            f.seek(self.last_log_position)
                            new_lines = f.readlines()
                            self.last_log_position = f.tell()

                            for line in new_lines:
                                raw_message = line.rstrip()
                                if not raw_message:
                                    continue

                                current_time = time.time()

                                if raw_message == self.last_message and (current_time - self.last_message_time) < 0.1:
                                    continue

                                self.last_message = raw_message
                                self.last_message_time = current_time

                                message = strip_minecraft_colors(raw_message)

                                time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', message)
                                timestamp = time_match.group(1) if time_match else datetime.now().strftime("%H:%M:%S")

                                log_entry = {"time": timestamp, "message": message}
                                self.log_buffer.append(log_entry)

                                if not self._should_filter_log(message):
                                    for callback in self.log_subscribers:
                                        try:
                                            await callback(log_entry)
                                        except Exception:
                                            pass

                    except Exception as e:
                        logger.error(f"Error reading log file: {e}")

                await asyncio.sleep(0.3)

        except asyncio.CancelledError:
            logger.info("Log tailer cancelled")
        except Exception as e:
            logger.error(f"Log tailer error: {e}")
        finally:
            logger.info("Log file tailer stopped")

    async def stop_server(self, force: bool = False) -> dict:
        """Stop the Minecraft server gracefully (detached mode)"""
        async with self.process_lock:
            if not self._is_server_running_sync():
                return {"success": False, "error": "Server is not running"}

            pid = self._get_server_pid_sync()

            stop_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": "[CORA] Stopping Minecraft server..."
            }
            self.log_buffer.append(stop_entry)
            for callback in self.log_subscribers:
                try:
                    await callback(stop_entry)
                except Exception:
                    pass

            self._save_console_history()

            try:
                rcon_config = get_rcon_config()
                if rcon_config.enabled and rcon_config.password:
                    try:
                        rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
                        if rcon.connect():
                            rcon.send_command("stop")
                            rcon.disconnect()

                            for i in range(30):
                                await asyncio.sleep(1)
                                if not self._is_server_running_sync():
                                    self._delete_pid_file()
                                    return {"success": True, "method": "rcon", "message": "Server stopped via RCON"}
                    except Exception as e:
                        logger.warning(f"RCON stop failed: {e}")

                if pid:
                    logger.info(f"Sending SIGTERM to PID {pid}")
                    os.kill(pid, signal.SIGTERM)

                    for i in range(15):
                        await asyncio.sleep(1)
                        if not self._is_server_running_sync():
                            self._delete_pid_file()
                            return {"success": True, "method": "sigterm", "message": "Server stopped via SIGTERM"}

                if force and pid:
                    logger.warning(f"Force killing PID {pid}")
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

                    await asyncio.sleep(1)
                    self._delete_pid_file()
                    return {"success": True, "method": "sigkill", "message": "Server force-killed"}

                return {"success": False, "error": "Could not stop server gracefully. Try force=true."}

            except Exception as e:
                return {"success": False, "error": str(e)}

    async def restart_server(
        self,
        ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
        require_rcon_ready: bool = True,
        start_retries: int = RESTART_START_RETRIES,
        retry_delay_sec: int = RESTART_RETRY_DELAY_SEC,
        source: str = "unknown",
    ) -> dict:
        """Restart the Minecraft server"""
        async with self.restart_guard_lock:
            now = datetime.now()
            if self.restart_in_progress:
                return {
                    "success": False,
                    "error": "Restart already in progress",
                    "error_code": "restart_in_progress",
                }

            cooldown_remaining = self._restart_cooldown_remaining_seconds(now)
            if cooldown_remaining > 0:
                return {
                    "success": False,
                    "error": f"Restart cooldown active. Retry after {cooldown_remaining}s",
                    "error_code": "restart_cooldown",
                    "retry_after_seconds": cooldown_remaining,
                    "last_restart_source": self.last_restart_source,
                }

            self.restart_in_progress = True

        restart_success = False
        try:
            restart_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": f"[CORA] Restarting Minecraft server... (source={source})"
            }
            self.log_buffer.append(restart_entry)
            for callback in self.log_subscribers:
                try:
                    await callback(restart_entry)
                except Exception:
                    pass

            stop_result = await self.stop_server()

            if not stop_result["success"] and "not running" not in stop_result.get("error", ""):
                return {"success": False, "error": f"Failed to stop: {stop_result.get('error')}"}

            await asyncio.sleep(3)

            recent_entries = list(self.log_buffer)[-5:] if len(self.log_buffer) > 5 else list(self.log_buffer)
            self.log_buffer.clear()
            for entry in recent_entries:
                self.log_buffer.append(entry)

            max_attempts = max(1, int(start_retries) + 1)
            delay_sec = max(0, int(retry_delay_sec))
            last_start_result = None

            for attempt in range(1, max_attempts + 1):
                start_result = await self.start_server(
                    wait_for_ready=True,
                    ready_timeout_sec=ready_timeout_sec,
                    require_rcon_ready=require_rcon_ready,
                )
                start_result["restart_start_attempt"] = attempt
                last_start_result = start_result

                if start_result.get("success"):
                    if attempt > 1:
                        start_result["message"] = (
                            f"{start_result.get('message', 'Server restart completed')} "
                            f"(start retry {attempt - 1})"
                        )
                    restart_success = True
                    return start_result

                error_code = start_result.get("error_code")
                retryable = error_code == "process_exited_early"
                if attempt < max_attempts and retryable:
                    logger.warning(
                        "Restart start attempt %s/%s failed (%s), retrying in %ss",
                        attempt,
                        max_attempts,
                        start_result.get("error", "unknown"),
                        delay_sec,
                    )
                    if delay_sec > 0:
                        await asyncio.sleep(delay_sec)
                    continue

                break

            assert last_start_result is not None
            return {
                "success": False,
                "error": (
                    f"Failed to start after {last_start_result.get('restart_start_attempt', 1)} "
                    f"attempt(s): {last_start_result.get('error', 'Unknown error')}"
                ),
                "error_code": last_start_result.get("error_code"),
                "ready_checks": last_start_result.get("ready_checks"),
                "restart_start_attempt": last_start_result.get("restart_start_attempt", 1),
            }
        finally:
            async with self.restart_guard_lock:
                self.restart_in_progress = False
                if restart_success:
                    self.last_restart_completed_at = datetime.now()
                    self.last_restart_source = source

    async def send_command(self, command: str) -> dict:
        """Send a command to the server via RCON"""
        if not self._is_server_running_sync():
            return {"success": False, "error": "Server is not running"}

        rcon_config = get_rcon_config()
        if not rcon_config.enabled or not rcon_config.password:
            return {"success": False, "error": "RCON is not enabled. Enable it in server.properties and restart the server."}

        try:
            rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
            if rcon.connect():
                response = rcon.send_command(command)
                rcon.disconnect()
                clean_response = strip_minecraft_colors(response)
                return {"success": True, "response": clean_response, "method": "rcon"}
            else:
                return {"success": False, "error": "Failed to connect to RCON"}
        except Exception as e:
            return {"success": False, "error": f"RCON error: {e}"}

    def get_server_status(self) -> ServerStatus:
        """Get comprehensive server status (with RCON caching to prevent spam)"""
        status = ServerStatus()
        rcon_config = get_rcon_config()
        process_running, pid, stale_pid_detected = self._get_process_snapshot_sync()
        status.running = process_running  # Backwards-compatible alias
        status.process_running = process_running
        status.pid = pid
        status.game_port_listening = self._is_port_listening(25565)
        status.rcon_port_listening = (
            self._is_port_listening(rcon_config.port) if rcon_config.enabled else False
        )
        status.healthy = status.process_running and status.game_port_listening

        if status.healthy:
            status.state_reason = "ok"
        elif stale_pid_detected:
            status.state_reason = "stale_pid"
        elif status.process_running and not status.game_port_listening:
            status.state_reason = "process_no_port"
        elif not status.process_running and status.game_port_listening:
            status.state_reason = "port_busy_no_process"
        elif status.process_running:
            status.state_reason = "starting"
        else:
            status.state_reason = "stopped"

        if status.process_running:

            now = time.time()
            cache = self.status_cache
            cache_valid = (cache is not None) and (now - self.status_cache_time) < STATUS_CACHE_TTL

            if cache_valid:
                assert cache is not None
                status.players_online = cache.get("players_online", 0)
                status.max_players = cache.get("max_players", 20)
            elif not self.status_refreshing:
                self.status_refreshing = True
                try:
                    if rcon_config.enabled and rcon_config.password:
                        rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
                        if rcon.connect():
                            response = rcon.send_command("list")
                            rcon.disconnect()

                            clean_response = strip_minecraft_colors(response)

                            match = re.search(r"(\d+)\s+of\s+(\d+)", clean_response)
                            if match:
                                status.players_online = int(match.group(1))
                                status.max_players = int(match.group(2))
                            else:
                                numbers = re.findall(r"(\d+)", clean_response)
                                if len(numbers) >= 2:
                                    status.max_players = int(numbers[0])
                                    status.players_online = int(numbers[1])

                            if status.players_online > 0 or status.max_players > 0:
                                self.status_cache = {
                                    "players_online": status.players_online,
                                    "max_players": status.max_players
                                }
                                self.status_cache_time = now
                except Exception as e:
                    logger.warning(f"Status check error: {e}")
                finally:
                    self.status_refreshing = False
            else:
                if self.status_cache:
                    status.players_online = self.status_cache.get("players_online", 0)
                    status.max_players = self.status_cache.get("max_players", 20)
        else:
            self.status_cache = None
            self.status_cache_time = 0

        props = load_server_properties()
        if status.max_players == 20:
            status.max_players = int(props.get("max-players", "20"))

        return status

    async def recover_server(
        self,
        ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
        require_rcon_ready: bool = True,
        start_retries: int = RESTART_START_RETRIES,
        retry_delay_sec: int = RESTART_RETRY_DELAY_SEC,
    ) -> dict:
        """
        Emergency recovery flow for "UI says running but server is unavailable":
        force-stop (if process exists) -> stale PID cleanup -> start with readiness checks.
        """
        steps: list[dict] = []
        before = self.get_server_status()
        steps.append({
            "step": "precheck",
            "process_running": before.process_running,
            "healthy": before.healthy,
            "state_reason": before.state_reason,
            "pid": before.pid,
        })

        if before.healthy:
            return {
                "success": True,
                "message": "Server already healthy",
                "steps": steps,
                "server": {
                    "running": before.running,
                    "process_running": before.process_running,
                    "healthy": before.healthy,
                    "state_reason": before.state_reason,
                    "pid": before.pid,
                    "game_port_listening": before.game_port_listening,
                    "rcon_port_listening": before.rcon_port_listening,
                },
            }

        if before.process_running:
            stop_result = await self.stop_server(force=True)
            steps.append({
                "step": "force_stop",
                "success": bool(stop_result.get("success")),
                "error": stop_result.get("error"),
                "method": stop_result.get("method"),
            })
            if not stop_result.get("success") and "not running" not in str(stop_result.get("error", "")):
                return {
                    "success": False,
                    "error": f"Recovery failed to stop existing process: {stop_result.get('error')}",
                    "steps": steps,
                }
            await asyncio.sleep(2)

        stale_pid_removed = False
        pid_from_file = self._read_pid_file()
        if pid_from_file and not self._is_minecraft_process(pid_from_file):
            self._delete_pid_file()
            stale_pid_removed = True
        steps.append({
            "step": "pid_cleanup",
            "stale_pid_removed": stale_pid_removed,
        })

        start_result = await self.restart_server(
            ready_timeout_sec=ready_timeout_sec,
            require_rcon_ready=require_rcon_ready,
            start_retries=start_retries,
            retry_delay_sec=retry_delay_sec,
        ) if before.process_running else await self.start_server(
            wait_for_ready=True,
            ready_timeout_sec=ready_timeout_sec,
            require_rcon_ready=require_rcon_ready,
        )

        steps.append({
            "step": "start",
            "success": bool(start_result.get("success")),
            "error": start_result.get("error"),
            "error_code": start_result.get("error_code"),
            "attempt": start_result.get("restart_start_attempt", 1),
        })

        if not start_result.get("success"):
            return {
                "success": False,
                "error": start_result.get("error", "Recovery failed to start server"),
                "error_code": start_result.get("error_code"),
                "steps": steps,
            }

        after = self.get_server_status()
        steps.append({
            "step": "postcheck",
            "healthy": after.healthy,
            "state_reason": after.state_reason,
            "process_running": after.process_running,
        })

        if not after.healthy:
            return {
                "success": False,
                "error": f"Recovery start returned success, but server is not healthy ({after.state_reason})",
                "steps": steps,
                "server": {
                    "running": after.running,
                    "process_running": after.process_running,
                    "healthy": after.healthy,
                    "state_reason": after.state_reason,
                    "pid": after.pid,
                    "game_port_listening": after.game_port_listening,
                    "rcon_port_listening": after.rcon_port_listening,
                },
            }

        return {
            "success": True,
            "message": "Server recovered successfully",
            "steps": steps,
            "server": {
                "running": after.running,
                "process_running": after.process_running,
                "healthy": after.healthy,
                "state_reason": after.state_reason,
                "pid": after.pid,
                "game_port_listening": after.game_port_listening,
                "rcon_port_listening": after.rcon_port_listening,
            },
        }

    def get_recent_logs(self, lines: int = 100, filtered: bool = True, offset: int = 0) -> list:
        """Get log entries with pagination support."""
        if filtered:
            all_logs = [log for log in self.log_buffer if not self._should_filter_log(log.get("message", ""))]
        else:
            all_logs = list(self.log_buffer)

        if offset > 0:
            if offset >= len(all_logs):
                return []
            older_logs = all_logs[:-offset]
            return older_logs[-lines:]
        else:
            return all_logs[-lines:]

    def subscribe_to_logs(self, callback: Callable):
        self.log_subscribers.append(callback)

    def unsubscribe_from_logs(self, callback: Callable):
        if callback in self.log_subscribers:
            self.log_subscribers.remove(callback)

    async def ensure_log_tailer_running(self):
        """Start log tailer if server is running (call on app startup)"""
        if self._is_server_running_sync():
            logger.info("Server already running, starting log tailer...")

            self.log_buffer.clear()

            if LATEST_LOG.exists():
                try:
                    with open(LATEST_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        for line in lines[-100:]:
                            raw_message = line.rstrip()
                            if not raw_message:
                                continue
                            time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', raw_message)
                            timestamp = time_match.group(1) if time_match else ""
                            message = strip_minecraft_colors(raw_message)
                            self.log_buffer.append({"time": timestamp, "message": message})
                    logger.info(f"Loaded {len(self.log_buffer)} recent logs from latest.log")
                except Exception as e:
                    logger.error(f"Failed to load recent logs: {e}")

            restart_marker = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": "[CORA] Web app restarted - reconnecting to server..."
            }
            self.log_buffer.append(restart_marker)

            if LATEST_LOG.exists():
                self.last_log_position = LATEST_LOG.stat().st_size

            if self.log_reader_task is None or self.log_reader_task.done():
                self.log_reader_task = asyncio.create_task(self._tail_log_file())
            return True
        return False


# =============================================================================
# Singleton + backwards-compatible public API
# =============================================================================

_manager = ServerManager()


def enable_rcon(password: str) -> bool:
    """Enable RCON in server.properties (requires server restart)"""
    if not password:
        return False
    if not SERVER_PROPERTIES.exists():
        return False

    with open(SERVER_PROPERTIES, "r") as f:
        content = f.read()

    replacements = {
        r"enable-rcon=\w+": "enable-rcon=true",
        r"rcon\.password=.*": f"rcon.password={password}",
    }

    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)

    with open(SERVER_PROPERTIES, "w") as f:
        f.write(content)

    return True


def update_start_script(new_jar_filename: str) -> bool:
    """Update start.sh with new JAR filename"""
    if not re.match(r'^paper-[\d.]+-\d+\.jar$', new_jar_filename):
        logger.warning(f"Rejected invalid JAR filename: {new_jar_filename}")
        return False

    if not START_SCRIPT.exists():
        return False

    try:
        with open(START_SCRIPT, "r") as f:
            content = f.read()

        new_content = re.sub(r"paper-[\d\.\-]+\.jar", new_jar_filename, content)

        with open(START_SCRIPT, "w") as f:
            f.write(new_content)

        logger.info(f"Updated start.sh to use {new_jar_filename}")
        return True

    except Exception as e:
        logger.error(f"Failed to update start.sh: {e}")
        return False


def read_latest_log(lines: int = 100) -> list:
    """Read the latest.log file directly"""
    logs = []
    if LATEST_LOG.exists():
        try:
            with open(LATEST_LOG, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    clean_line = strip_minecraft_colors(line.rstrip())
                    time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', clean_line)
                    timestamp = time_match.group(1) if time_match else ""
                    logs.append({"time": timestamp, "message": clean_line})
        except Exception as e:
            logs.append({"time": "", "message": f"Error reading log: {e}"})
    return logs


# --- Delegate to singleton (preserves existing call sites) ---

def is_server_running() -> bool:
    return _manager._is_server_running_sync()

def get_server_pid() -> Optional[int]:
    return _manager._get_server_pid_sync()

async def start_server(
    wait_for_ready: bool = False,
    ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
    require_rcon_ready: bool = True,
) -> dict:
    return await _manager.start_server(
        wait_for_ready=wait_for_ready,
        ready_timeout_sec=ready_timeout_sec,
        require_rcon_ready=require_rcon_ready,
    )

async def stop_server(force: bool = False) -> dict:
    return await _manager.stop_server(force=force)

async def restart_server(
    ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
    require_rcon_ready: bool = True,
    start_retries: int = RESTART_START_RETRIES,
    retry_delay_sec: int = RESTART_RETRY_DELAY_SEC,
    source: str = "unknown",
) -> dict:
    return await _manager.restart_server(
        ready_timeout_sec=ready_timeout_sec,
        require_rcon_ready=require_rcon_ready,
        start_retries=start_retries,
        retry_delay_sec=retry_delay_sec,
        source=source,
    )

async def recover_server(
    ready_timeout_sec: int = DEFAULT_READY_TIMEOUT_SEC,
    require_rcon_ready: bool = True,
    start_retries: int = RESTART_START_RETRIES,
    retry_delay_sec: int = RESTART_RETRY_DELAY_SEC,
) -> dict:
    return await _manager.recover_server(
        ready_timeout_sec=ready_timeout_sec,
        require_rcon_ready=require_rcon_ready,
        start_retries=start_retries,
        retry_delay_sec=retry_delay_sec,
    )

async def send_command(command: str) -> dict:
    return await _manager.send_command(command)

def get_server_status() -> ServerStatus:
    return _manager.get_server_status()

def get_recent_logs(lines: int = 100, filtered: bool = True, offset: int = 0) -> list:
    return _manager.get_recent_logs(lines, filtered=filtered, offset=offset)

def subscribe_to_logs(callback: Callable):
    _manager.subscribe_to_logs(callback)

def unsubscribe_from_logs(callback: Callable):
    _manager.unsubscribe_from_logs(callback)

async def ensure_log_tailer_running():
    return await _manager.ensure_log_tailer_running()
