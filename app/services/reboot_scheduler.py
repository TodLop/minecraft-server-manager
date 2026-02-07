# app/services/reboot_scheduler.py
"""
Minecraft Server Automation Service

Implements automatic maintenance logic from Project Octopus:
1. Reboot: If 0 users for >6 hours → Execute stop and restart
2. Reboot: If uptime >12 hours (with users online) → Announce restart timer, then restart
3. Maintenance: Auto-delete CoreProtect logs older than configured days

Features:
- Configurable thresholds via admin panel
- In-game countdown warnings before restart
- CoreProtect log purge automation
- Detailed action logging with success/failure status
- Real-time status monitoring
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from enum import Enum

from app.core.config import DATA_DIR
from app.services import minecraft_server

# Configuration file path
CONFIG_FILE = DATA_DIR / "reboot_scheduler_config.json"
LOG_FILE = DATA_DIR / "reboot_scheduler_log.json"


class SchedulerState(str, Enum):
    """Current state of the scheduler"""
    DISABLED = "disabled"
    MONITORING = "monitoring"
    COUNTDOWN_EMPTY = "countdown_empty"      # Counting down for empty server restart
    COUNTDOWN_UPTIME = "countdown_uptime"    # Counting down for uptime-based restart
    RESTARTING = "restarting"
    ERROR = "error"


@dataclass
class SchedulerConfig:
    """Scheduler configuration"""
    enabled: bool = True

    # Trigger 1: Empty server restart
    empty_server_enabled: bool = True
    empty_hours_threshold: float = 6.0  # Restart if empty for this many hours

    # Trigger 2: Uptime-based restart
    uptime_restart_enabled: bool = True
    max_uptime_hours: float = 12.0  # Restart after this many hours of uptime

    # Countdown settings
    countdown_minutes: int = 5  # Warning time before restart
    warning_intervals: List[int] = field(default_factory=lambda: [5, 3, 1])  # Minutes to warn at

    # CoreProtect maintenance
    coreprotect_purge_enabled: bool = True
    coreprotect_retention_days: int = 30  # Delete logs older than this
    coreprotect_purge_hour: int = 4  # Hour of day to run purge (0-23, default 4 AM)
    coreprotect_last_purge: Optional[str] = None  # ISO timestamp of last purge

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SchedulerConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SchedulerStatus:
    """Current scheduler status"""
    state: SchedulerState = SchedulerState.DISABLED
    server_running: bool = False
    players_online: int = 0

    # Timing info
    server_started_at: Optional[str] = None
    uptime_seconds: int = 0
    uptime_formatted: str = "0h 0m"

    empty_since: Optional[str] = None
    empty_seconds: int = 0
    empty_formatted: str = "0h 0m"

    # Countdown info (when in countdown state)
    countdown_reason: Optional[str] = None
    countdown_remaining_seconds: int = 0
    countdown_formatted: str = ""
    next_warning_at: Optional[str] = None

    # Next action prediction
    next_action: Optional[str] = None
    next_action_at: Optional[str] = None

    # CoreProtect purge status
    coreprotect_last_purge: Optional[str] = None
    coreprotect_next_purge: Optional[str] = None
    coreprotect_purge_running: bool = False

    last_check: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["state"] = self.state.value
        return data


@dataclass
class ActionLog:
    """Log entry for scheduler actions"""
    timestamp: str
    action: str  # "restart_empty", "restart_uptime", "warning_sent", "config_changed", "error"
    status: str  # "success", "failed", "info"
    details: str
    trigger_reason: Optional[str] = None
    players_affected: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class RebootScheduler:
    """Manages automatic server restarts"""

    def __init__(self):
        self.config = SchedulerConfig()
        self.status = SchedulerStatus()
        self.logs: List[ActionLog] = []

        # Tracking state
        self._server_start_time: Optional[datetime] = None
        self._empty_since: Optional[datetime] = None
        self._last_player_count: int = 0
        self._countdown_start: Optional[datetime] = None
        self._countdown_target: Optional[datetime] = None
        self._warnings_sent: set = set()  # Track which warnings have been sent

        # Background task
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # Load saved config and logs
        self._load_config()
        self._load_logs()

    def _load_config(self):
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.config = SchedulerConfig.from_dict(data)
            except Exception as e:
                print(f"[RebootScheduler] Failed to load config: {e}")

    def _save_config(self):
        """Save configuration to file"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config.to_dict(), f, indent=2)
        except Exception as e:
            print(f"[RebootScheduler] Failed to save config: {e}")

    def _load_logs(self):
        """Load recent logs from file"""
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r") as f:
                    data = json.load(f)
                    self.logs = [ActionLog(**log) for log in data[-100:]]  # Keep last 100
            except Exception as e:
                print(f"[RebootScheduler] Failed to load logs: {e}")

    def _save_logs(self):
        """Save logs to file"""
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "w") as f:
                json.dump([log.to_dict() for log in self.logs[-100:]], f, indent=2)
        except Exception as e:
            print(f"[RebootScheduler] Failed to save logs: {e}")

    def _add_log(self, action: str, status: str, details: str,
                 trigger_reason: str = None, players_affected: int = 0):
        """Add a log entry"""
        log = ActionLog(
            timestamp=datetime.now().isoformat(),
            action=action,
            status=status,
            details=details,
            trigger_reason=trigger_reason,
            players_affected=players_affected
        )
        self.logs.append(log)
        self._save_logs()
        print(f"[RebootScheduler] {action}: {details} ({status})")

    def _format_duration(self, seconds: int) -> str:
        """Format seconds as human-readable duration"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"

    async def start(self):
        """Start the scheduler background task"""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._add_log("scheduler_start", "success", "Reboot scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self._add_log("scheduler_stop", "success", "Reboot scheduler stopped")

    def update_config(self, **kwargs) -> dict:
        """Update scheduler configuration"""
        old_enabled = self.config.enabled

        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        self._save_config()

        # Log the change
        changes = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self._add_log("config_changed", "success", f"Configuration updated: {changes}")

        return {"success": True, "config": self.config.to_dict()}

    def get_config(self) -> dict:
        """Get current configuration"""
        return self.config.to_dict()

    def _update_realtime_status(self):
        """Update status with realtime calculations (called on API request)"""
        now = datetime.now()
        self.status.last_check = now.isoformat()

        # Get current server status
        server_status = minecraft_server.get_server_status()
        self.status.server_running = server_status.running
        self.status.players_online = server_status.players_online if server_status.running else 0

        # Calculate uptime if server is running and we have a start time
        if server_status.running and self._server_start_time:
            uptime = now - self._server_start_time
            self.status.uptime_seconds = int(uptime.total_seconds())
            self.status.uptime_formatted = self._format_duration(self.status.uptime_seconds)
            self.status.server_started_at = self._server_start_time.isoformat()

        # Calculate empty time if applicable
        if self._empty_since and self.status.players_online == 0:
            empty_time = now - self._empty_since
            self.status.empty_seconds = int(empty_time.total_seconds())
            self.status.empty_formatted = self._format_duration(self.status.empty_seconds)
            self.status.empty_since = self._empty_since.isoformat()

        # Update countdown remaining if in countdown state
        if self._countdown_target and self.status.state in [SchedulerState.COUNTDOWN_EMPTY, SchedulerState.COUNTDOWN_UPTIME]:
            remaining = (self._countdown_target - now).total_seconds()
            self.status.countdown_remaining_seconds = max(0, int(remaining))
            self.status.countdown_formatted = self._format_duration(self.status.countdown_remaining_seconds)

    def get_status(self) -> dict:
        """Get current scheduler status (with realtime update)"""
        self._update_realtime_status()
        return self.status.to_dict()

    def get_logs(self, limit: int = 50) -> List[dict]:
        """Get recent action logs"""
        return [log.to_dict() for log in self.logs[-limit:]][::-1]  # Newest first

    async def _monitor_loop(self):
        """Main monitoring loop - runs every 30 seconds"""
        print("[RebootScheduler] Monitor loop started")

        while self._running:
            try:
                await self._check_and_act()
            except Exception as e:
                self.status.state = SchedulerState.ERROR
                self.status.error_message = str(e)
                self._add_log("error", "failed", f"Monitor error: {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _check_and_act(self):
        """Check server status and take action if needed"""
        now = datetime.now()
        self.status.last_check = now.isoformat()

        # Get server status
        server_status = minecraft_server.get_server_status()
        self.status.server_running = server_status.running
        self.status.players_online = server_status.players_online if server_status.running else 0

        # Check CoreProtect purge (runs independently of reboot scheduler)
        await self._check_coreprotect_purge()

        # Handle disabled state
        if not self.config.enabled:
            self.status.state = SchedulerState.DISABLED
            self.status.next_action = None
            return

        # Handle server not running
        if not server_status.running:
            self.status.state = SchedulerState.MONITORING
            self.status.next_action = "Waiting for server to start"
            self._reset_tracking()
            return

        # Track server start time
        if self._server_start_time is None:
            self._server_start_time = now
            self._add_log("server_detected", "info", "Server running detected, starting tracking")

        # Calculate uptime
        uptime = now - self._server_start_time
        self.status.uptime_seconds = int(uptime.total_seconds())
        self.status.uptime_formatted = self._format_duration(self.status.uptime_seconds)
        self.status.server_started_at = self._server_start_time.isoformat()

        # Track empty time
        if self.status.players_online == 0:
            if self._empty_since is None:
                self._empty_since = now
            empty_time = now - self._empty_since
            self.status.empty_seconds = int(empty_time.total_seconds())
            self.status.empty_formatted = self._format_duration(self.status.empty_seconds)
            self.status.empty_since = self._empty_since.isoformat()
        else:
            self._empty_since = None
            self.status.empty_seconds = 0
            self.status.empty_formatted = "0s"
            self.status.empty_since = None

        # Check if we're in a countdown
        if self.status.state in [SchedulerState.COUNTDOWN_EMPTY, SchedulerState.COUNTDOWN_UPTIME]:
            await self._handle_countdown(now)
            return

        # Check triggers
        self.status.state = SchedulerState.MONITORING

        # Trigger 1: Empty server for too long
        if self.config.empty_server_enabled and self._empty_since:
            empty_hours = self.status.empty_seconds / 3600
            if empty_hours >= self.config.empty_hours_threshold:
                await self._start_countdown("empty", f"Server empty for {self._format_duration(self.status.empty_seconds)}")
                return
            else:
                remaining = (self.config.empty_hours_threshold * 3600) - self.status.empty_seconds
                self.status.next_action = f"Empty server restart in {self._format_duration(int(remaining))}"
                self.status.next_action_at = (now + timedelta(seconds=remaining)).isoformat()

        # Trigger 2: Uptime too long (only if players online)
        if self.config.uptime_restart_enabled and self.status.players_online > 0:
            uptime_hours = self.status.uptime_seconds / 3600
            if uptime_hours >= self.config.max_uptime_hours:
                await self._start_countdown("uptime", f"Server uptime {self._format_duration(self.status.uptime_seconds)}")
                return
            else:
                remaining = (self.config.max_uptime_hours * 3600) - self.status.uptime_seconds
                if self.status.next_action is None or "uptime" not in self.status.next_action.lower():
                    self.status.next_action = f"Uptime restart in {self._format_duration(int(remaining))}"
                    self.status.next_action_at = (now + timedelta(seconds=remaining)).isoformat()

    async def _start_countdown(self, reason: str, details: str):
        """Start countdown for restart"""
        now = datetime.now()

        if reason == "empty":
            self.status.state = SchedulerState.COUNTDOWN_EMPTY
            self.status.countdown_reason = "Empty server threshold reached"
            # For empty server, do immediate restart (no players to warn)
            self._countdown_target = now
            self._add_log("restart_triggered", "info",
                         f"Empty server restart triggered: {details}",
                         trigger_reason=reason)
            await self._execute_restart(reason)
        else:
            self.status.state = SchedulerState.COUNTDOWN_UPTIME
            self.status.countdown_reason = "Uptime threshold reached"
            self._countdown_start = now
            self._countdown_target = now + timedelta(minutes=self.config.countdown_minutes)
            self._warnings_sent = set()

            self._add_log("countdown_started", "info",
                         f"Restart countdown started ({self.config.countdown_minutes}min): {details}",
                         trigger_reason=reason,
                         players_affected=self.status.players_online)

            # Send initial warning
            await self._send_warning(self.config.countdown_minutes)

    async def _handle_countdown(self, now: datetime):
        """Handle countdown state - send warnings and execute restart"""
        if self._countdown_target is None:
            self.status.state = SchedulerState.MONITORING
            return

        remaining = (self._countdown_target - now).total_seconds()
        self.status.countdown_remaining_seconds = max(0, int(remaining))
        self.status.countdown_formatted = self._format_duration(self.status.countdown_remaining_seconds)

        # Check if countdown complete
        if remaining <= 0:
            await self._execute_restart(
                "empty" if self.status.state == SchedulerState.COUNTDOWN_EMPTY else "uptime"
            )
            return

        # Send warnings at configured intervals
        remaining_minutes = remaining / 60
        for warning_minute in self.config.warning_intervals:
            if warning_minute not in self._warnings_sent and remaining_minutes <= warning_minute:
                await self._send_warning(warning_minute)
                self._warnings_sent.add(warning_minute)

        # 30 second and 10 second warnings
        if remaining <= 30 and "30s" not in self._warnings_sent:
            await self._send_warning(0.5)  # 30 seconds
            self._warnings_sent.add("30s")
        if remaining <= 10 and "10s" not in self._warnings_sent:
            await self._send_warning(0.17)  # 10 seconds
            self._warnings_sent.add("10s")

    async def _send_warning(self, minutes: float):
        """Send in-game warning to players"""
        if minutes >= 1:
            time_str = f"{int(minutes)} minute{'s' if minutes != 1 else ''}"
        else:
            seconds = int(minutes * 60)
            time_str = f"{seconds} seconds"

        # Send title (big text on screen)
        title_cmd = f'title @a title {{"text":"⚠ SERVER RESTART","color":"gold","bold":true}}'
        subtitle_cmd = f'title @a subtitle {{"text":"in {time_str}","color":"yellow"}}'

        # Send chat message
        chat_cmd = f'say §6[Auto-Restart] §eServer will restart in {time_str}. Please find a safe spot!'

        try:
            await minecraft_server.send_command(title_cmd)
            await minecraft_server.send_command(subtitle_cmd)
            await minecraft_server.send_command(chat_cmd)

            self._add_log("warning_sent", "success",
                         f"Restart warning sent: {time_str}",
                         players_affected=self.status.players_online)
        except Exception as e:
            self._add_log("warning_sent", "failed", f"Failed to send warning: {e}")

    async def _execute_restart(self, reason: str):
        """Execute the actual server restart"""
        self.status.state = SchedulerState.RESTARTING
        players = self.status.players_online

        self._add_log("restart_started", "info",
                     f"Executing restart (reason: {reason})",
                     trigger_reason=reason,
                     players_affected=players)

        try:
            # Send final message
            if players > 0:
                await minecraft_server.send_command('say §c[Auto-Restart] §fRestarting now! See you soon!')
                await asyncio.sleep(2)  # Give players time to see the message

            # Execute restart
            result = await minecraft_server.restart_server()

            if result.get("success"):
                self._add_log("restart_completed", "success",
                             f"Server restart completed successfully (was {reason})",
                             trigger_reason=reason,
                             players_affected=players)

                # Reset tracking
                self._reset_tracking()
                self._server_start_time = datetime.now()  # Will be accurate after server starts

            else:
                error = result.get("error", "Unknown error")
                self._add_log("restart_failed", "failed",
                             f"Restart failed: {error}",
                             trigger_reason=reason,
                             players_affected=players)
                self.status.state = SchedulerState.ERROR
                self.status.error_message = error

        except Exception as e:
            self._add_log("restart_failed", "failed", f"Restart exception: {e}",
                         trigger_reason=reason)
            self.status.state = SchedulerState.ERROR
            self.status.error_message = str(e)

    def _reset_tracking(self):
        """Reset tracking state"""
        self._server_start_time = None
        self._empty_since = None
        self._countdown_start = None
        self._countdown_target = None
        self._warnings_sent = set()
        self.status.countdown_reason = None
        self.status.countdown_remaining_seconds = 0
        self.status.countdown_formatted = ""

    async def trigger_manual_restart(self, reason: str = "manual") -> dict:
        """Manually trigger a restart with countdown"""
        if not self.status.server_running:
            return {"success": False, "error": "Server is not running"}

        if self.status.state in [SchedulerState.COUNTDOWN_EMPTY,
                                  SchedulerState.COUNTDOWN_UPTIME,
                                  SchedulerState.RESTARTING]:
            return {"success": False, "error": f"Already in {self.status.state.value} state"}

        self._add_log("manual_restart", "info",
                     f"Manual restart triggered by admin",
                     trigger_reason=reason,
                     players_affected=self.status.players_online)

        if self.status.players_online > 0:
            # Start countdown with warnings
            await self._start_countdown("uptime", "Manual restart requested")
            return {"success": True, "message": f"Restart countdown started ({self.config.countdown_minutes} minutes)"}
        else:
            # Immediate restart for empty server
            await self._execute_restart("manual")
            return {"success": True, "message": "Restart executed (no players online)"}

    def cancel_countdown(self) -> dict:
        """Cancel an active countdown"""
        if self.status.state not in [SchedulerState.COUNTDOWN_EMPTY, SchedulerState.COUNTDOWN_UPTIME]:
            return {"success": False, "error": "No countdown active"}

        self._add_log("countdown_cancelled", "info",
                     f"Countdown cancelled by admin",
                     players_affected=self.status.players_online)

        self._countdown_start = None
        self._countdown_target = None
        self._warnings_sent = set()
        self.status.state = SchedulerState.MONITORING
        self.status.countdown_reason = None
        self.status.countdown_remaining_seconds = 0

        # Notify players
        asyncio.create_task(
            minecraft_server.send_command('say §a[Auto-Restart] §fRestart has been cancelled!')
        )

        return {"success": True, "message": "Countdown cancelled"}

    # =========================================================================
    # CoreProtect Purge Methods
    # =========================================================================

    def _should_run_purge(self) -> bool:
        """Check if CoreProtect purge should run"""
        if not self.config.coreprotect_purge_enabled:
            return False

        if not self.status.server_running:
            return False

        now = datetime.now()

        # Check if it's the configured hour
        if now.hour != self.config.coreprotect_purge_hour:
            return False

        # Check if we already ran today
        if self.config.coreprotect_last_purge:
            try:
                last_purge = datetime.fromisoformat(self.config.coreprotect_last_purge)
                if last_purge.date() == now.date():
                    return False  # Already ran today
            except (ValueError, TypeError):
                pass

        return True

    def _get_next_purge_time(self) -> Optional[str]:
        """Calculate when the next purge will run"""
        if not self.config.coreprotect_purge_enabled:
            return None

        now = datetime.now()
        next_purge = now.replace(
            hour=self.config.coreprotect_purge_hour,
            minute=0,
            second=0,
            microsecond=0
        )

        # If we've passed today's purge time, schedule for tomorrow
        if now.hour >= self.config.coreprotect_purge_hour:
            next_purge += timedelta(days=1)

        return next_purge.isoformat()

    async def _check_coreprotect_purge(self):
        """Check and execute CoreProtect purge if needed"""
        if self._should_run_purge():
            await self.execute_coreprotect_purge()

        # Update next purge time in status
        self.status.coreprotect_next_purge = self._get_next_purge_time()
        self.status.coreprotect_last_purge = self.config.coreprotect_last_purge

    async def execute_coreprotect_purge(self, manual: bool = False) -> dict:
        """
        Execute CoreProtect log purge.

        CoreProtect requires confirmation, so we send:
        1. /co purge t:30d
        2. Wait for response
        3. /co purge t:30d confirm
        """
        if not self.status.server_running:
            return {"success": False, "error": "Server is not running"}

        if self.status.coreprotect_purge_running:
            return {"success": False, "error": "Purge already in progress"}

        self.status.coreprotect_purge_running = True
        retention_days = self.config.coreprotect_retention_days

        self._add_log(
            "coreprotect_purge_started",
            "info",
            f"CoreProtect purge started: deleting logs older than {retention_days} days" +
            (" (manual)" if manual else " (scheduled)")
        )

        try:
            # Step 1: Send initial purge command
            purge_cmd = f"co purge t:{retention_days}d"
            result1 = await minecraft_server.send_command(purge_cmd)

            if not result1.get("success"):
                raise Exception(f"Initial purge command failed: {result1.get('error')}")

            # Wait a moment for CoreProtect to process
            await asyncio.sleep(2)

            # Step 2: Send confirmation command
            confirm_cmd = f"co purge t:{retention_days}d confirm"
            result2 = await minecraft_server.send_command(confirm_cmd)

            if not result2.get("success"):
                raise Exception(f"Purge confirmation failed: {result2.get('error')}")

            # Update last purge time
            now = datetime.now()
            self.config.coreprotect_last_purge = now.isoformat()
            self._save_config()

            self.status.coreprotect_last_purge = now.isoformat()

            self._add_log(
                "coreprotect_purge_completed",
                "success",
                f"CoreProtect purge completed: deleted logs older than {retention_days} days"
            )

            return {
                "success": True,
                "message": f"Purge completed: deleted logs older than {retention_days} days",
                "retention_days": retention_days,
                "purged_at": now.isoformat()
            }

        except Exception as e:
            self._add_log(
                "coreprotect_purge_failed",
                "failed",
                f"CoreProtect purge failed: {str(e)}"
            )
            return {"success": False, "error": str(e)}

        finally:
            self.status.coreprotect_purge_running = False

    def get_coreprotect_status(self) -> dict:
        """Get CoreProtect purge status"""
        return {
            "enabled": self.config.coreprotect_purge_enabled,
            "retention_days": self.config.coreprotect_retention_days,
            "purge_hour": self.config.coreprotect_purge_hour,
            "last_purge": self.config.coreprotect_last_purge,
            "next_purge": self._get_next_purge_time(),
            "purge_running": self.status.coreprotect_purge_running
        }


# Global singleton instance
_scheduler: Optional[RebootScheduler] = None


def get_scheduler() -> RebootScheduler:
    """Get the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = RebootScheduler()
    return _scheduler


async def start_scheduler():
    """Start the scheduler (call from app lifespan)"""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """Stop the scheduler (call from app lifespan)"""
    scheduler = get_scheduler()
    await scheduler.stop()
