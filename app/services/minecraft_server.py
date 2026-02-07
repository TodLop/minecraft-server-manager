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
import os
import re
import signal
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List
from collections import deque

from app.core.config import MINECRAFT_SERVER_PATH

# Export an alias for external modules (admin.py uses minecraft_server.SERVER_DIR)
SERVER_DIR = MINECRAFT_SERVER_PATH

# Configuration (paths derived from central config)
SERVER_PROPERTIES = MINECRAFT_SERVER_PATH / "server.properties"
START_SCRIPT = MINECRAFT_SERVER_PATH / "start.sh"
LOGS_DIR = MINECRAFT_SERVER_PATH / "logs"
LATEST_LOG = LOGS_DIR / "latest.log"
CONSOLE_HISTORY_FILE = LOGS_DIR / "cora_console_history.jsonl"  # Persistent console history
PID_FILE = MINECRAFT_SERVER_PATH / "server.pid"  # Track detached process PID

# Process tracking (detached mode - server runs independently)
_log_subscribers: List[Callable] = []
_log_buffer: deque = deque(maxlen=500)  # Keep last 500 lines
_process_lock = asyncio.Lock()
_log_reader_task: Optional[asyncio.Task] = None  # Log file tailer task
_last_log_position: int = 0  # Track position in log file
_last_log_inode: Optional[int] = None  # Track log file inode for rotation detection

# Status cache to prevent RCON spam
_status_cache: Optional[dict] = None
_status_cache_time: float = 0
_status_refreshing: bool = False  # Prevent concurrent RCON calls
STATUS_CACHE_TTL = 5.0  # Cache player count for 5 seconds (reduced for better responsiveness)

# Deduplication: track last message with timestamp for millisecond-based filtering
_last_message: str = ""
_last_message_time: float = 0.0

# Log messages to filter out (noise)
LOG_FILTER_PATTERNS = [
    "Thread RCON Client",
    "Rcon issued server command: /list",
]


def _should_filter_log(message: str) -> bool:
    """Check if a log message should be filtered out"""
    for pattern in LOG_FILTER_PATTERNS:
        if pattern in message:
            return True
    return False


def _save_console_history():
    """Save current console buffer to persistent file"""
    try:
        # Ensure logs directory exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Save all log entries as JSON lines
        with open(CONSOLE_HISTORY_FILE, 'w', encoding='utf-8') as f:
            for entry in _log_buffer:
                f.write(json.dumps(entry) + '\n')

        print(f"[Server] Saved {len(_log_buffer)} log entries to {CONSOLE_HISTORY_FILE}")
        return True
    except Exception as e:
        print(f"[Server] Failed to save console history: {e}")
        return False


def _load_console_history():
    """Load console history from persistent file into buffer"""
    global _log_buffer

    if not CONSOLE_HISTORY_FILE.exists():
        print("[Server] No console history file found, starting fresh")
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
                    _log_buffer.append(entry)
                    loaded_count += 1
                except json.JSONDecodeError:
                    continue

        print(f"[Server] Loaded {loaded_count} log entries from history")
        return True
    except Exception as e:
        print(f"[Server] Failed to load console history: {e}")
        return False


def strip_minecraft_colors(text: str) -> str:
    """Strip Minecraft color/formatting codes (§X) from text"""
    # § followed by any character (0-9, a-f, k-o, r, x for hex, etc.)
    return re.sub(r'§.', '', text)


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


@dataclass
class RCONConfig:
    """RCON configuration"""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 25575
    password: str = ""


def load_server_properties() -> dict:
    """Load server.properties file"""
    props = {}
    if SERVER_PROPERTIES.exists():
        with open(SERVER_PROPERTIES, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    props[key.strip()] = value.strip()
    return props


def get_rcon_config() -> RCONConfig:
    """Get RCON configuration from server.properties"""
    props = load_server_properties()
    return RCONConfig(
        enabled=props.get("enable-rcon", "false").lower() == "true",
        host="127.0.0.1",
        port=int(props.get("rcon.port", "25575")),
        password=props.get("rcon.password", "")
    )


def enable_rcon(password: str = "cora_admin_rcon") -> bool:
    """Enable RCON in server.properties (requires server restart)"""
    if not SERVER_PROPERTIES.exists():
        return False

    with open(SERVER_PROPERTIES, "r") as f:
        content = f.read()

    # Update RCON settings
    replacements = {
        r"enable-rcon=\w+": "enable-rcon=true",
        r"rcon\.password=.*": f"rcon.password={password}",
    }

    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)

    with open(SERVER_PROPERTIES, "w") as f:
        f.write(content)

    return True


class RCONClient:
    """Minecraft RCON protocol client"""

    SERVERDATA_AUTH = 3
    SERVERDATA_AUTH_RESPONSE = 2
    SERVERDATA_EXECCOMMAND = 2
    SERVERDATA_RESPONSE_VALUE = 0
    MAX_PACKET_SIZE = 4096  # Standard RCON max packet size

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.socket: Optional[socket.socket] = None
        self.request_id = 0

    def _pack_packet(self, packet_type: int, payload: str) -> bytes:
        """Pack a packet for sending"""
        self.request_id += 1
        payload_bytes = payload.encode("utf-8") + b"\x00\x00"
        length = 4 + 4 + len(payload_bytes)
        return struct.pack("<iii", length, self.request_id, packet_type) + payload_bytes

    def _read_packet(self) -> tuple:
        """Read a packet from the socket"""
        # Read length
        length_data = self.socket.recv(4)
        if len(length_data) < 4:
            raise ConnectionError("Connection lost")

        length = struct.unpack("<i", length_data)[0]
        if length < 0 or length > self.MAX_PACKET_SIZE:
            raise ConnectionError(f"RCON packet size out of bounds: {length}")

        # Read rest of packet
        data = self.socket.recv(length)
        request_id = struct.unpack("<i", data[0:4])[0]
        packet_type = struct.unpack("<i", data[4:8])[0]
        payload = data[8:-2].decode("utf-8")

        return request_id, packet_type, payload

    def connect(self) -> bool:
        """Connect and authenticate"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))

            # Send auth packet
            self.socket.send(self._pack_packet(self.SERVERDATA_AUTH, self.password))

            # Read response
            request_id, packet_type, _ = self._read_packet()

            # Auth success if request_id matches (failure returns -1)
            return request_id != -1

        except Exception as e:
            print(f"[RCON] Connection failed: {e}")
            return False

    def send_command(self, command: str) -> str:
        """Send a command and get response"""
        if not self.socket:
            raise ConnectionError("Not connected")

        try:
            self.socket.send(self._pack_packet(self.SERVERDATA_EXECCOMMAND, command))
            _, _, payload = self._read_packet()
            return payload
        except Exception as e:
            raise ConnectionError(f"Command failed: {e}")

    def disconnect(self):
        """Close connection"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None


def _read_pid_file() -> Optional[int]:
    """Read PID from file"""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            return pid
        except (ValueError, IOError):
            pass
    return None


def _write_pid_file(pid: int) -> None:
    """Write PID to file"""
    PID_FILE.write_text(str(pid))


def _delete_pid_file() -> None:
    """Delete PID file"""
    if PID_FILE.exists():
        PID_FILE.unlink()


def _is_minecraft_process(pid: int) -> bool:
    """Check if a process with given PID is actually the Minecraft server"""
    try:
        # First check if process exists
        os.kill(pid, 0)
    except OSError:
        return False

    # Now verify it's actually a Java/Minecraft process by checking command line
    try:
        # On macOS/Linux, read /proc/{pid}/cmdline or use ps
        if Path(f"/proc/{pid}/cmdline").exists():
            # Linux: read from /proc
            with open(f"/proc/{pid}/cmdline", "r") as f:
                cmdline = f.read()
                return "java" in cmdline.lower() and "paper" in cmdline.lower()
        else:
            # macOS: use ps command
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                cmdline = result.stdout.lower()
                return "java" in cmdline and "paper" in cmdline
    except Exception as e:
        print(f"[Server] Error checking process {pid}: {e}")

    return False


def _find_minecraft_pid() -> Optional[int]:
    """Find the Minecraft server PID using pgrep"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "java.*paper.*\\.jar"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None


def is_server_running() -> bool:
    """Check if the Minecraft server process is running"""
    # First check PID file
    pid = _read_pid_file()
    if pid and _is_minecraft_process(pid):
        return True

    # PID file exists but process is not Minecraft - clean it up
    if pid:
        print(f"[Server] Stale PID file detected (PID {pid} is not Minecraft), cleaning up")
        _delete_pid_file()

    # Fall back to pgrep for servers started externally
    found_pid = _find_minecraft_pid()
    if found_pid:
        print(f"[Server] Found Minecraft process via pgrep: PID {found_pid}")
        _write_pid_file(found_pid)
        return True

    return False


def get_server_pid() -> Optional[int]:
    """Get the server process PID"""
    # Check PID file first
    pid = _read_pid_file()
    if pid and _is_minecraft_process(pid):
        return pid

    # Fall back to pgrep
    return _find_minecraft_pid()


async def start_server() -> dict:
    """Start the Minecraft server as a detached process"""
    global _log_buffer, _log_reader_task, _last_log_position, _last_log_inode

    async with _process_lock:
        if is_server_running():
            return {"success": False, "error": "Server is already running"}

        if not START_SCRIPT.exists():
            return {"success": False, "error": "start.sh not found"}

        try:
            # Cancel existing log tailer if any
            if _log_reader_task and not _log_reader_task.done():
                _log_reader_task.cancel()
                try:
                    await asyncio.wait_for(_log_reader_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            # Clear buffer and start fresh (don't load old history)
            _log_buffer.clear()
            # Note: Removed _load_console_history() to avoid showing old logs
            
            # Start reading from CURRENT end of log file (skip old content)
            if LATEST_LOG.exists():
                _last_log_position = LATEST_LOG.stat().st_size
                _last_log_inode = LATEST_LOG.stat().st_ino
            else:
                _last_log_position = 0
                _last_log_inode = None

            # Add session separator and startup message to buffer
            separator_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": "[CORA] =============================================="
            }
            start_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": "[CORA] Starting Minecraft server..."
            }
            _log_buffer.append(separator_entry)
            _log_buffer.append(start_entry)

            # Notify subscribers of startup
            for callback in _log_subscribers:
                try:
                    await callback(start_entry)
                except:
                    pass

            # Start the server as a DETACHED process
            # - start_new_session=True: Creates new process group, survives parent exit
            # - stdin/stdout/stderr=DEVNULL: No pipe attachment (we read from log file)
            process = subprocess.Popen(
                ["sh", str(START_SCRIPT)],
                cwd=str(MINECRAFT_SERVER_PATH),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process
            )

            # Save PID to file for tracking
            _write_pid_file(process.pid)

            # Start log file tailer task
            _log_reader_task = asyncio.create_task(_tail_log_file())

            return {
                "success": True,
                "pid": process.pid,
                "message": "Server starting (detached mode)..."
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def _tail_log_file():
    """Background task to tail the server log file"""
    global _log_buffer, _last_log_position, _last_log_inode, _last_message, _last_message_time

    print("[Server] Log file tailer started")
    _last_message = ""
    _last_message_time = 0.0

    try:
        while True:
            # Check if server is still running
            if not is_server_running():
                print("[Server] Server stopped, tailer exiting")
                # Add a final log entry to show server stopped
                stop_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": "[CORA] Server process stopped"
                }
                _log_buffer.append(stop_entry)
                for callback in _log_subscribers:
                    try:
                        await callback(stop_entry)
                    except:
                        pass
                break

            # Read new lines from log file
            if LATEST_LOG.exists():
                try:
                    # Check for log file rotation (new file created)
                    current_inode = LATEST_LOG.stat().st_ino
                    current_size = LATEST_LOG.stat().st_size

                    # Detect rotation: inode changed OR file got smaller (truncated/new file)
                    if _last_log_inode is not None and (current_inode != _last_log_inode or current_size < _last_log_position):
                        print(f"[Server] Log file rotated (inode: {_last_log_inode} -> {current_inode}, size: {_last_log_position} -> {current_size})")
                        _last_log_position = 0  # Start from beginning of new file
                        # Add rotation marker to log
                        rotation_entry = {
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "message": "[CORA] Log file rotated - new server session"
                        }
                        _log_buffer.append(rotation_entry)
                        for callback in _log_subscribers:
                            try:
                                await callback(rotation_entry)
                            except:
                                pass

                    _last_log_inode = current_inode

                    with open(LATEST_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                        # Seek to last known position
                        f.seek(_last_log_position)
                        new_lines = f.readlines()
                        _last_log_position = f.tell()

                        for line in new_lines:
                            raw_message = line.rstrip()
                            if not raw_message:
                                continue

                            current_time = time.time()

                            # Time-based deduplication
                            if raw_message == _last_message and (current_time - _last_message_time) < 0.1:
                                continue

                            _last_message = raw_message
                            _last_message_time = current_time

                            # Strip Minecraft color codes
                            message = strip_minecraft_colors(raw_message)

                            # Extract timestamp from log line if present (e.g., "[12:34:56 INFO]:")
                            time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', message)
                            if time_match:
                                timestamp = time_match.group(1)
                            else:
                                timestamp = datetime.now().strftime("%H:%M:%S")

                            log_entry = {"time": timestamp, "message": message}

                            # Store in buffer
                            _log_buffer.append(log_entry)

                            # Notify subscribers if not filtered
                            if not _should_filter_log(message):
                                for callback in _log_subscribers:
                                    try:
                                        await callback(log_entry)
                                    except:
                                        pass

                except Exception as e:
                    print(f"[Server] Error reading log file: {e}")

            # Poll interval (adjust for responsiveness vs CPU usage)
            await asyncio.sleep(0.3)  # Reduced for better responsiveness

    except asyncio.CancelledError:
        print("[Server] Log tailer cancelled")
    except Exception as e:
        print(f"[Server] Log tailer error: {e}")
    finally:
        print("[Server] Log file tailer stopped")


async def stop_server(force: bool = False) -> dict:
    """Stop the Minecraft server gracefully (detached mode)"""
    global _log_reader_task

    async with _process_lock:
        if not is_server_running():
            return {"success": False, "error": "Server is not running"}

        pid = get_server_pid()

        # Add stop message to log
        stop_entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": "[CORA] Stopping Minecraft server..."
        }
        _log_buffer.append(stop_entry)
        for callback in _log_subscribers:
            try:
                await callback(stop_entry)
            except:
                pass

        # Save console history before stopping
        _save_console_history()

        try:
            # Try RCON first (most graceful - sends /stop command)
            rcon_config = get_rcon_config()
            if rcon_config.enabled and rcon_config.password:
                try:
                    rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
                    if rcon.connect():
                        rcon.send_command("stop")
                        rcon.disconnect()

                        # Wait for process to exit
                        for i in range(30):  # 30 second timeout
                            await asyncio.sleep(1)
                            if not is_server_running():
                                _delete_pid_file()
                                return {"success": True, "method": "rcon", "message": "Server stopped via RCON"}
                except Exception as e:
                    print(f"[Server] RCON stop failed: {e}")

            # No stdin in detached mode - try SIGTERM directly
            if pid:
                print(f"[Server] Sending SIGTERM to PID {pid}")
                os.kill(pid, signal.SIGTERM)

                # Wait for graceful shutdown
                for i in range(15):  # 15 second timeout for SIGTERM
                    await asyncio.sleep(1)
                    if not is_server_running():
                        _delete_pid_file()
                        return {"success": True, "method": "sigterm", "message": "Server stopped via SIGTERM"}

            # Force kill if requested or graceful failed
            if force and pid:
                print(f"[Server] Force killing PID {pid}")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Already dead

                await asyncio.sleep(1)
                _delete_pid_file()
                return {"success": True, "method": "sigkill", "message": "Server force-killed"}

            return {"success": False, "error": "Could not stop server gracefully. Try force=true."}

        except Exception as e:
            return {"success": False, "error": str(e)}


async def restart_server() -> dict:
    """Restart the Minecraft server"""
    global _log_buffer

    # Add restart message to log
    restart_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": "[CORA] Restarting Minecraft server..."
    }
    _log_buffer.append(restart_entry)
    for callback in _log_subscribers:
        try:
            await callback(restart_entry)
        except:
            pass

    stop_result = await stop_server()

    if not stop_result["success"] and "not running" not in stop_result.get("error", ""):
        return {"success": False, "error": f"Failed to stop: {stop_result.get('error')}"}

    # Wait a moment before starting (server needs time to release port)
    await asyncio.sleep(3)

    # Clear buffer before starting fresh (but keep the restart message context)
    # Keep last few entries for context
    recent_entries = list(_log_buffer)[-5:] if len(_log_buffer) > 5 else list(_log_buffer)
    _log_buffer.clear()
    for entry in recent_entries:
        _log_buffer.append(entry)

    return await start_server()


async def send_command(command: str) -> dict:
    """Send a command to the server via RCON (detached mode - no stdin)"""
    if not is_server_running():
        return {"success": False, "error": "Server is not running"}

    # RCON is the only way to send commands in detached mode
    rcon_config = get_rcon_config()
    if not rcon_config.enabled or not rcon_config.password:
        return {"success": False, "error": "RCON is not enabled. Enable it in server.properties and restart the server."}

    try:
        rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
        if rcon.connect():
            response = rcon.send_command(command)
            rcon.disconnect()
            # Strip Minecraft color codes for clean display
            clean_response = strip_minecraft_colors(response)
            return {"success": True, "response": clean_response, "method": "rcon"}
        else:
            return {"success": False, "error": "Failed to connect to RCON"}
    except Exception as e:
        return {"success": False, "error": f"RCON error: {e}"}


def get_server_status() -> ServerStatus:
    """Get comprehensive server status (with RCON caching to prevent spam)"""
    global _status_cache, _status_cache_time, _status_refreshing

    status = ServerStatus()
    status.running = is_server_running()

    if status.running:
        status.pid = get_server_pid()

        # Check cache first to prevent RCON spam
        now = time.time()
        cache_valid = _status_cache and (now - _status_cache_time) < STATUS_CACHE_TTL

        if cache_valid:
            # Use cached player count
            status.players_online = _status_cache.get("players_online", 0)
            status.max_players = _status_cache.get("max_players", 20)
        elif not _status_refreshing:
            # Only query RCON if not already refreshing (prevent concurrent calls)
            _status_refreshing = True
            try:
                rcon_config = get_rcon_config()
                if rcon_config.enabled and rcon_config.password:
                    rcon = RCONClient(rcon_config.host, rcon_config.port, rcon_config.password)
                    if rcon.connect():
                        response = rcon.send_command("list")
                        rcon.disconnect()

                        # Strip Minecraft color codes for parsing
                        clean_response = strip_minecraft_colors(response)

                        # Try multiple formats:
                        # English: "There are X of Y players online"
                        # Korean (Essentials): "최대 Y 명이 접속 가능하고, X 명의 플레이어가 접속중"

                        match = re.search(r"(\d+)\s+of\s+(\d+)", clean_response)
                        if match:
                            # English format: X of Y
                            status.players_online = int(match.group(1))
                            status.max_players = int(match.group(2))
                        else:
                            # Korean format: 최대 Y ... X 명의 플레이어
                            # Extract all numbers and use: first = max, second = online
                            numbers = re.findall(r"(\d+)", clean_response)
                            if len(numbers) >= 2:
                                status.max_players = int(numbers[0])
                                status.players_online = int(numbers[1])

                        if status.players_online > 0 or status.max_players > 0:
                            # Update cache
                            _status_cache = {
                                "players_online": status.players_online,
                                "max_players": status.max_players
                            }
                            _status_cache_time = now
            except Exception as e:
                print(f"[STATUS] Error: {e}")
            finally:
                _status_refreshing = False
        else:
            # Another request is refreshing, use stale cache if available
            if _status_cache:
                status.players_online = _status_cache.get("players_online", 0)
                status.max_players = _status_cache.get("max_players", 20)
    else:
        # Server not running, clear cache
        _status_cache = None
        _status_cache_time = 0

    # Get max_players from server properties as fallback
    props = load_server_properties()
    if status.max_players == 20:  # Only override if using default
        status.max_players = int(props.get("max-players", "20"))

    return status


def get_recent_logs(lines: int = 100, filtered: bool = True, offset: int = 0) -> list:
    """Get log entries with pagination support.

    Args:
        lines: Number of log lines to return
        filtered: Whether to filter out RCON noise
        offset: Skip the most recent N logs (for loading older logs)
    """
    if filtered:
        all_logs = [log for log in _log_buffer if not _should_filter_log(log.get("message", ""))]
    else:
        all_logs = list(_log_buffer)

    if offset > 0:
        # Get older logs: skip the most recent 'offset' logs, then take 'lines' from the end of what remains
        if offset >= len(all_logs):
            return []  # No more older logs
        older_logs = all_logs[:-offset]  # Everything except the most recent 'offset' logs
        return older_logs[-lines:]  # Take the last 'lines' from the older portion
    else:
        # Get most recent logs
        return all_logs[-lines:]


def subscribe_to_logs(callback: Callable):
    """Subscribe to real-time log updates"""
    _log_subscribers.append(callback)


def unsubscribe_from_logs(callback: Callable):
    """Unsubscribe from log updates"""
    if callback in _log_subscribers:
        _log_subscribers.remove(callback)


def update_start_script(new_jar_filename: str) -> bool:
    """Update start.sh with new JAR filename"""
    if not re.match(r'^paper-[\d.]+-\d+\.jar$', new_jar_filename):
        print(f"[Server] Rejected invalid JAR filename: {new_jar_filename}")
        return False

    if not START_SCRIPT.exists():
        return False

    try:
        with open(START_SCRIPT, "r") as f:
            content = f.read()

        # Replace paper*.jar with new filename
        new_content = re.sub(
            r"paper-[\d\.\-]+\.jar",
            new_jar_filename,
            content
        )

        with open(START_SCRIPT, "w") as f:
            f.write(new_content)

        print(f"[Server] Updated start.sh to use {new_jar_filename}")
        return True

    except Exception as e:
        print(f"[Server] Failed to update start.sh: {e}")
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
                    # Extract timestamp from log line if present
                    time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', clean_line)
                    timestamp = time_match.group(1) if time_match else ""
                    logs.append({"time": timestamp, "message": clean_line})
        except Exception as e:
            logs.append({"time": "", "message": f"Error reading log: {e}"})

    return logs


async def ensure_log_tailer_running():
    """Start log tailer if server is running (call on app startup)"""
    global _log_reader_task, _last_log_position

    if is_server_running():
        print("[Server] Server already running, starting log tailer...")

        # Clear any stale buffer and load fresh logs from the actual log file
        _log_buffer.clear()
        
        # Load recent lines from the ACTUAL log file (not stale history file)
        if LATEST_LOG.exists():
            try:
                with open(LATEST_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    # Get last 100 lines for initial display
                    for line in lines[-100:]:
                        raw_message = line.rstrip()
                        if not raw_message:
                            continue
                        # Extract timestamp from log line if present
                        time_match = re.match(r'\[(\d{2}:\d{2}:\d{2})', raw_message)
                        timestamp = time_match.group(1) if time_match else ""
                        message = strip_minecraft_colors(raw_message)
                        _log_buffer.append({"time": timestamp, "message": message})
                print(f"[Server] Loaded {len(_log_buffer)} recent logs from latest.log")
            except Exception as e:
                print(f"[Server] Failed to load recent logs: {e}")

        # Add app restart marker
        restart_marker = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": "[CORA] Web app restarted - reconnecting to server..."
        }
        _log_buffer.append(restart_marker)

        # Start from end of file to get only NEW logs going forward
        if LATEST_LOG.exists():
            _last_log_position = LATEST_LOG.stat().st_size

        if _log_reader_task is None or _log_reader_task.done():
            _log_reader_task = asyncio.create_task(_tail_log_file())
        return True
    return False
