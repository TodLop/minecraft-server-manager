"""Tests for reboot scheduler grace period and auto-recovery logic."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services import minecraft_server
from app.services import reboot_scheduler


def _make_scheduler(monkeypatch, tmp_path):
    """Create a scheduler with isolated config/log files."""
    monkeypatch.setattr(reboot_scheduler, "CONFIG_FILE", tmp_path / "cfg.json")
    monkeypatch.setattr(reboot_scheduler, "LOG_FILE", tmp_path / "log.json")
    sched = reboot_scheduler.RebootScheduler()
    sched.config.enabled = True
    sched.config.empty_server_enabled = True
    sched.config.empty_hours_threshold = 1.0
    sched.config.uptime_restart_enabled = True
    sched.config.max_uptime_hours = 8.0
    sched.config.restart_grace_minutes = 30
    return sched


@dataclass
class _FakeServerStatus:
    running: bool = True
    process_running: bool = True
    game_port_listening: bool = True
    rcon_port_listening: bool = True
    healthy: bool = True
    state_reason: str = "ok"
    pid: int = 12345
    players_online: int = 0
    max_players: int = 20


def _patch_status(monkeypatch, status):
    """Monkey-patch minecraft_server.get_server_status to return *status*."""
    monkeypatch.setattr(reboot_scheduler.minecraft_server, "get_server_status", lambda: status)


def _patch_commands(monkeypatch):
    """Patch send_command and restart_server to no-ops."""
    async def _noop_cmd(cmd):
        return {"success": True}

    async def _noop_restart(**kwargs):
        return {"success": True, "message": "restarted"}

    monkeypatch.setattr(reboot_scheduler.minecraft_server, "send_command", _noop_cmd)
    monkeypatch.setattr(reboot_scheduler.minecraft_server, "restart_server", _noop_restart)


# ── Grace period blocks empty-server restart ──


def test_grace_period_blocks_empty_restart(monkeypatch, tmp_path):
    """After a restart, the scheduler should NOT trigger an empty-server
    restart during the grace period, even if the server has been empty
    longer than empty_hours_threshold."""
    sched = _make_scheduler(monkeypatch, tmp_path)
    _patch_status(monkeypatch, _FakeServerStatus(players_online=0))
    _patch_commands(monkeypatch)

    # Simulate: restart just completed 5 minutes ago
    sched._last_restart_completed_at = datetime.now() - timedelta(minutes=5)
    # Simulate: server has been empty for 2 hours (would normally trigger restart)
    sched._empty_since = datetime.now() - timedelta(hours=2)
    sched._server_start_time = datetime.now() - timedelta(hours=2)

    asyncio.run(sched._check_and_act())

    # Should stay in MONITORING (grace period active), NOT start a countdown
    assert sched.status.state == reboot_scheduler.SchedulerState.MONITORING
    assert "grace period" in (sched.status.next_action or "").lower()


# ── Grace period expires and restart triggers normally ──


def test_grace_period_expires(monkeypatch, tmp_path):
    """After the grace period ends, the empty-server restart should trigger
    normally."""
    sched = _make_scheduler(monkeypatch, tmp_path)
    _patch_status(monkeypatch, _FakeServerStatus(players_online=0))
    _patch_commands(monkeypatch)

    # Grace period expired 5 minutes ago
    sched._last_restart_completed_at = datetime.now() - timedelta(minutes=35)
    # Server empty for 2 hours
    sched._empty_since = datetime.now() - timedelta(hours=2)
    sched._server_start_time = datetime.now() - timedelta(hours=2)

    asyncio.run(sched._check_and_act())

    # Should have triggered restart (state becomes RESTARTING or COUNTDOWN)
    assert sched.status.state in (
        reboot_scheduler.SchedulerState.COUNTDOWN_EMPTY,
        reboot_scheduler.SchedulerState.RESTARTING,
    )


# ── Zombie process auto-recovery ──


def test_degraded_auto_recover(monkeypatch, tmp_path):
    """When server is stuck in process_no_port for > 3 minutes, the scheduler
    should automatically trigger recover_server()."""
    sched = _make_scheduler(monkeypatch, tmp_path)

    degraded_status = _FakeServerStatus(
        running=False,
        process_running=True,
        game_port_listening=False,
        healthy=False,
        state_reason="process_no_port",
    )
    _patch_status(monkeypatch, degraded_status)

    recover_called = {"called": False}

    async def _fake_recover(**kwargs):
        recover_called["called"] = True
        return {"success": True, "message": "recovered"}

    monkeypatch.setattr(reboot_scheduler.minecraft_server, "recover_server", _fake_recover)

    # Simulate: degraded for 4 minutes already
    sched._degraded_since = datetime.now() - timedelta(minutes=4)

    asyncio.run(sched._check_and_act())

    assert recover_called["called"], "recover_server should have been called"
    assert sched._degraded_since is None, "should reset after recovery"
    # Grace period should be set after auto-recovery
    assert sched._last_restart_completed_at is not None


def test_degraded_waits_before_recovery(monkeypatch, tmp_path):
    """When server just entered process_no_port, the scheduler should wait
    before recovering (not trigger immediately)."""
    sched = _make_scheduler(monkeypatch, tmp_path)

    degraded_status = _FakeServerStatus(
        running=False,
        process_running=True,
        game_port_listening=False,
        healthy=False,
        state_reason="process_no_port",
    )
    _patch_status(monkeypatch, degraded_status)

    recover_called = {"called": False}

    async def _fake_recover(**kwargs):
        recover_called["called"] = True
        return {"success": True}

    monkeypatch.setattr(reboot_scheduler.minecraft_server, "recover_server", _fake_recover)

    # Simulate: degraded for only 1 minute
    sched._degraded_since = datetime.now() - timedelta(minutes=1)

    asyncio.run(sched._check_and_act())

    assert not recover_called["called"], "should NOT recover yet (only 1 min elapsed)"
    assert sched._degraded_since is not None, "should still be tracking degraded state"
    assert "degraded" in (sched.status.next_action or "").lower()
