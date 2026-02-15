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
import subprocess
import time
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
CONSOLE_HISTORY_FILE = LOGS_DIR / "minecraft_console_history.jsonl"
PID_FILE = MINECRAFT_SERVER_PATH / "server.pid"

# Log messages to filter out (noise)
LOG_FILTER_PATTERNS = [
    "Thread RCON Client",
    "Rcon issued server command: /list",
]

# Status cache TTL
STATUS_CACHE_TTL = 5.0


@dataclass
class ServerStatus:
    """Server status information"""
    running: bool = False
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

    def _is_server_running_sync(self) -> bool:
        """Sync version — shells out to ps/pgrep. Use is_server_running() for async."""
        pid = self._read_pid_file()
        if pid and self._is_minecraft_process(pid):
            return True

        if pid:
            logger.warning(f"Stale PID file detected (PID {pid} is not Minecraft), cleaning up")
            self._delete_pid_file()

        found_pid = self._find_minecraft_pid()
        if found_pid:
            logger.info(f"Found Minecraft process via pgrep: PID {found_pid}")
            self._write_pid_file(found_pid)
            return True

        return False

    def _get_server_pid_sync(self) -> Optional[int]:
        pid = self._read_pid_file()
        if pid and self._is_minecraft_process(pid):
            return pid
        return self._find_minecraft_pid()

    # ------------------------------------------------------------------
    # Async wrappers (run blocking I/O in thread pool)
    # ------------------------------------------------------------------

    async def is_server_running_async(self) -> bool:
        return await asyncio.to_thread(self._is_server_running_sync)

    async def get_server_pid_async(self) -> Optional[int]:
        return await asyncio.to_thread(self._get_server_pid_sync)

    # ------------------------------------------------------------------
    # Server control
    # ------------------------------------------------------------------

    async def start_server(self) -> dict:
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
                    "message": "[ServerManager] =============================================="
                }
                start_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": "[ServerManager] Starting Minecraft server..."
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

                return {
                    "success": True,
                    "pid": process.pid,
                    "message": "Server starting (detached mode)..."
                }

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
                        "message": "[ServerManager] Server process stopped"
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
                                "message": "[ServerManager] Log file rotated - new server session"
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
                "message": "[ServerManager] Stopping Minecraft server..."
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

    async def restart_server(self) -> dict:
        """Restart the Minecraft server"""
        restart_entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": "[ServerManager] Restarting Minecraft server..."
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

        return await self.start_server()

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
        status.running = self._is_server_running_sync()

        if status.running:
            status.pid = self._get_server_pid_sync()

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
                    rcon_config = get_rcon_config()
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
                "message": "[ServerManager] Web app restarted - reconnecting to server..."
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

async def start_server() -> dict:
    return await _manager.start_server()

async def stop_server(force: bool = False) -> dict:
    return await _manager.stop_server(force=force)

async def restart_server() -> dict:
    return await _manager.restart_server()

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
