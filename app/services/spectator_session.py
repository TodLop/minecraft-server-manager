# app/services/spectator_session.py
"""
Spectator Session Service

Manages spectator sessions for staff to observe suspicious players.
Features:
- Request/approval workflow for non-confirmed cheaters
- Auto-approval for confirmed cheaters
- Integration with CORASpectator Minecraft plugin via RCON
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict
import threading

from app.core.config import DATA_DIR, ROOT_DIR
from app.services.watchlist import get_watchlist_entry_by_player, get_watchlist_entry

logger = logging.getLogger(__name__)

# Spectator sessions file path
SESSIONS_FILE = DATA_DIR / "spectator_sessions.json"

# Audit log file path (shared with investigation)
LOGS_DIR = ROOT_DIR / "logs"
AUDIT_LOG_FILE = LOGS_DIR / "investigation_audit.log"

# Thread lock for file operations
_file_lock = threading.Lock()

# Configure audit logger
def _setup_audit_logger():
    """Set up dedicated audit logger for spectator sessions"""
    logger = logging.getLogger("spectator_audit")

    if not logger.handlers:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(AUDIT_LOG_FILE, encoding='utf-8')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | SPECTATOR | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger

audit_logger = _setup_audit_logger()

# Valid spectator session statuses
SPECTATOR_STATUSES = frozenset([
    "pending",      # Awaiting admin approval
    "approved",     # Approved, ready to start
    "denied",       # Denied by admin
    "active",       # Currently spectating
    "completed",    # Session ended normally
    "revoked"       # Force-ended by admin
])

# Valid end reasons
END_REASONS = frozenset(["manual", "timeout", "player_left", "revoked", "error"])

# Default session duration
DEFAULT_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 60


@dataclass
class SpectatorSession:
    """Represents a spectator session request/session"""
    id: str
    watchlist_id: Optional[str]          # Reference to watchlist entry
    player: str                          # Target player
    requested_by: str                    # Staff email
    requested_at: str                    # ISO timestamp
    request_reason: str                  # Why spectating
    status: str                          # pending | approved | denied | active | completed | revoked
    auto_approved: bool = False          # True if confirmed-cheater
    approved_by: Optional[str] = None    # Admin who approved
    approved_at: Optional[str] = None
    denied_by: Optional[str] = None
    denied_at: Optional[str] = None
    denial_reason: Optional[str] = None
    max_duration_minutes: int = DEFAULT_DURATION_MINUTES
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    end_reason: Optional[str] = None     # manual | timeout | player_left | revoked


def _load_sessions() -> dict:
    """Load sessions from JSON file"""
    if not SESSIONS_FILE.exists():
        return {"sessions": []}

    try:
        with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Error loading file: %s", e)
        return {"sessions": []}


def _save_sessions(data: dict) -> bool:
    """Save sessions to JSON file"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        logger.error("Error saving file: %s", e)
        return False


def _log_audit(action: str, user_email: str, player: str = None, details: str = None):
    """Log an action to the audit file"""
    parts = [f"action={action}", f"user={user_email}"]
    if player:
        parts.append(f"player={player}")
    if details:
        parts.append(f"details={details}")

    audit_logger.info(" | ".join(parts))


def should_auto_approve(watchlist_entry) -> bool:
    """
    Determine if a spectator request should be auto-approved.

    Auto-approve for confirmed cheaters only.
    """
    if watchlist_entry and watchlist_entry.level == "confirmed-cheater":
        return True
    return False


def request_spectator(
    player: str,
    staff_email: str,
    reason: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    is_admin: bool = False
) -> Optional[SpectatorSession]:
    """
    Request a spectator session for a player.

    For confirmed cheaters, the request is auto-approved.
    For others, it requires admin approval.

    Args:
        player: Target Minecraft username
        staff_email: Requesting staff email
        reason: Reason for spectating
        duration_minutes: Requested session duration
        is_admin: Whether the requester is an admin

    Returns:
        SpectatorSession if created
    """
    player_lower = player.lower()

    # Get watchlist entry
    watchlist_entry = get_watchlist_entry_by_player(player_lower, active_only=True)

    # Staff can only request for watchlisted players
    if not is_admin and not watchlist_entry:
        _log_audit("request_denied", staff_email, player_lower, "Player not on watchlist")
        return None

    # Validate duration
    duration_minutes = min(max(5, duration_minutes), MAX_DURATION_MINUTES)

    # Check for auto-approval
    auto_approve = should_auto_approve(watchlist_entry)

    with _file_lock:
        data = _load_sessions()

        # Check if there's already an active or pending session for this player
        for s in data["sessions"]:
            if s.get("player") == player_lower:
                if s.get("status") in ["pending", "approved", "active"]:
                    return None  # Already has active/pending session

        # Check if staff already has an active spectator session
        for s in data["sessions"]:
            if s.get("requested_by") == staff_email and s.get("status") == "active":
                return None  # Already spectating someone

        session = SpectatorSession(
            id=f"spec_{str(uuid.uuid4())[:8]}",
            watchlist_id=watchlist_entry.id if watchlist_entry else None,
            player=player_lower,
            requested_by=staff_email,
            requested_at=datetime.now().isoformat(),
            request_reason=reason,
            status="approved" if auto_approve else "pending",
            auto_approved=auto_approve,
            max_duration_minutes=duration_minutes
        )

        if auto_approve:
            session.approved_at = datetime.now().isoformat()
            session.approved_by = "system"
            _log_audit(
                "spectator_auto_approved",
                staff_email,
                player_lower,
                f"session_id={session.id}, level=confirmed-cheater"
            )
        else:
            _log_audit(
                "spectator_requested",
                staff_email,
                player_lower,
                f"session_id={session.id}, awaiting_approval"
            )

        data["sessions"].append(asdict(session))
        _save_sessions(data)

    return session


def get_session_by_id(session_id: str) -> Optional[SpectatorSession]:
    """Get a spectator session by ID"""
    with _file_lock:
        data = _load_sessions()

    for s in data.get("sessions", []):
        if s.get("id") == session_id:
            return SpectatorSession(**s)

    return None


def approve_request(
    session_id: str,
    admin_email: str,
    duration_override: int = None
) -> Optional[SpectatorSession]:
    """
    Approve a pending spectator request.

    Args:
        session_id: Session ID
        admin_email: Approving admin's email
        duration_override: Optional duration override

    Returns:
        Approved SpectatorSession if successful
    """
    with _file_lock:
        data = _load_sessions()

        for s in data["sessions"]:
            if s.get("id") == session_id:
                if s.get("status") != "pending":
                    return None  # Can only approve pending

                s["status"] = "approved"
                s["approved_by"] = admin_email
                s["approved_at"] = datetime.now().isoformat()

                if duration_override:
                    s["max_duration_minutes"] = min(duration_override, MAX_DURATION_MINUTES)

                _save_sessions(data)

                _log_audit(
                    "spectator_approved",
                    admin_email,
                    s.get("player"),
                    f"session_id={session_id}, requested_by={s.get('requested_by')}"
                )

                return SpectatorSession(**s)

    return None


def deny_request(
    session_id: str,
    admin_email: str,
    reason: str = None
) -> Optional[SpectatorSession]:
    """
    Deny a pending spectator request.

    Args:
        session_id: Session ID
        admin_email: Denying admin's email
        reason: Optional denial reason

    Returns:
        Denied SpectatorSession if successful
    """
    with _file_lock:
        data = _load_sessions()

        for s in data["sessions"]:
            if s.get("id") == session_id:
                if s.get("status") != "pending":
                    return None  # Can only deny pending

                s["status"] = "denied"
                s["denied_by"] = admin_email
                s["denied_at"] = datetime.now().isoformat()
                s["denial_reason"] = reason

                _save_sessions(data)

                _log_audit(
                    "spectator_denied",
                    admin_email,
                    s.get("player"),
                    f"session_id={session_id}, reason={reason}"
                )

                return SpectatorSession(**s)

    return None


async def start_spectator_session(
    session_id: str,
    staff_email: str,
    staff_minecraft_name: str
) -> dict:
    """
    Start an approved spectator session via RCON.

    Sends command to CORASpectator plugin:
    cora-spectate start <staff> <target> <duration_seconds>

    Args:
        session_id: Session ID
        staff_email: Must match requester
        staff_minecraft_name: Staff's Minecraft username

    Returns:
        Result dict with success status and message
    """
    from app.services.minecraft_server import send_command

    session = get_session_by_id(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if session.status != "approved":
        return {"success": False, "error": f"Session is not approved (status: {session.status})"}

    if session.requested_by != staff_email:
        return {"success": False, "error": "You are not the requester of this session"}

    # Calculate duration in seconds
    duration_seconds = session.max_duration_minutes * 60

    # Send RCON command to start spectator
    command = f"cora-spectate start {staff_minecraft_name} {session.player} {duration_seconds}"
    result = await send_command(command)

    if result.get("success"):
        # Update session status
        with _file_lock:
            data = _load_sessions()
            for s in data["sessions"]:
                if s.get("id") == session_id:
                    s["status"] = "active"
                    s["started_at"] = datetime.now().isoformat()
                    _save_sessions(data)
                    break

        _log_audit(
            "spectator_started",
            staff_email,
            session.player,
            f"session_id={session_id}, staff_mc={staff_minecraft_name}, duration={session.max_duration_minutes}m"
        )

        return {
            "success": True,
            "message": f"Spectator session started. You have {session.max_duration_minutes} minutes.",
            "session_id": session_id
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "Failed to start spectator session via RCON")
        }


async def end_spectator_session(
    session_id: str,
    user_email: str,
    reason: str = "manual",
    staff_minecraft_name: str = None,
    is_admin: bool = False
) -> dict:
    """
    End a spectator session.

    Staff can end their own sessions.
    Admins can end any session (revoke).

    Args:
        session_id: Session ID
        user_email: User ending the session
        reason: End reason (manual, timeout, player_left, revoked)
        staff_minecraft_name: Minecraft name to teleport back
        is_admin: Whether user is admin

    Returns:
        Result dict
    """
    from app.services.minecraft_server import send_command

    session = get_session_by_id(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if session.status != "active":
        return {"success": False, "error": f"Session is not active (status: {session.status})"}

    # Check authorization
    if not is_admin and session.requested_by != user_email:
        return {"success": False, "error": "You are not authorized to end this session"}

    # Determine end status
    end_status = "revoked" if is_admin and session.requested_by != user_email else "completed"

    # Send RCON command to end spectator
    if staff_minecraft_name:
        command = f"cora-spectate end {staff_minecraft_name}"
        await send_command(command)

    # Update session
    with _file_lock:
        data = _load_sessions()
        for s in data["sessions"]:
            if s.get("id") == session_id:
                s["status"] = end_status
                s["ended_at"] = datetime.now().isoformat()
                s["end_reason"] = reason
                _save_sessions(data)
                break

    _log_audit(
        f"spectator_{end_status}",
        user_email,
        session.player,
        f"session_id={session_id}, reason={reason}"
    )

    return {"success": True, "message": f"Spectator session {end_status}"}


def get_pending_requests() -> List[SpectatorSession]:
    """Get all pending spectator requests"""
    with _file_lock:
        data = _load_sessions()

    return [
        SpectatorSession(**s) for s in data.get("sessions", [])
        if s.get("status") == "pending"
    ]


def get_active_sessions() -> List[SpectatorSession]:
    """Get all active spectator sessions"""
    with _file_lock:
        data = _load_sessions()

    return [
        SpectatorSession(**s) for s in data.get("sessions", [])
        if s.get("status") == "active"
    ]


def get_approved_sessions() -> List[SpectatorSession]:
    """Get all approved but not started sessions"""
    with _file_lock:
        data = _load_sessions()

    return [
        SpectatorSession(**s) for s in data.get("sessions", [])
        if s.get("status") == "approved"
    ]


def get_staff_sessions(staff_email: str) -> List[SpectatorSession]:
    """Get all sessions for a specific staff member"""
    with _file_lock:
        data = _load_sessions()

    sessions = [
        SpectatorSession(**s) for s in data.get("sessions", [])
        if s.get("requested_by") == staff_email
    ]

    sessions.sort(key=lambda s: s.requested_at, reverse=True)
    return sessions


def get_player_sessions(player: str) -> List[SpectatorSession]:
    """Get all spectator sessions targeting a player"""
    player_lower = player.lower()

    with _file_lock:
        data = _load_sessions()

    sessions = [
        SpectatorSession(**s) for s in data.get("sessions", [])
        if s.get("player") == player_lower
    ]

    sessions.sort(key=lambda s: s.requested_at, reverse=True)
    return sessions


def get_recent_sessions(limit: int = 50) -> List[SpectatorSession]:
    """Get recent spectator sessions"""
    with _file_lock:
        data = _load_sessions()

    sessions = [SpectatorSession(**s) for s in data.get("sessions", [])]
    sessions.sort(key=lambda s: s.requested_at, reverse=True)
    return sessions[:limit]


def get_spectator_stats() -> dict:
    """Get spectator session statistics"""
    with _file_lock:
        data = _load_sessions()

    sessions = data.get("sessions", [])

    return {
        "total": len(sessions),
        "pending": len([s for s in sessions if s.get("status") == "pending"]),
        "approved": len([s for s in sessions if s.get("status") == "approved"]),
        "active": len([s for s in sessions if s.get("status") == "active"]),
        "completed": len([s for s in sessions if s.get("status") == "completed"]),
        "denied": len([s for s in sessions if s.get("status") == "denied"]),
        "revoked": len([s for s in sessions if s.get("status") == "revoked"]),
        "auto_approved": len([s for s in sessions if s.get("auto_approved")])
    }


async def revoke_session(session_id: str, admin_email: str) -> dict:
    """Admin-only: Force-end any spectator session"""
    return await end_spectator_session(
        session_id=session_id,
        user_email=admin_email,
        reason="revoked",
        is_admin=True
    )


async def check_spectator_status() -> dict:
    """
    Check status of all spectator sessions via RCON.

    Calls: cora-spectate status
    """
    from app.services.minecraft_server import send_command

    result = await send_command("cora-spectate status")
    return result
