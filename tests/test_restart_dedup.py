import asyncio
from datetime import datetime

from app.services import minecraft_server
from app.services import operations
from app.services import reboot_scheduler


def _setup_operation_test_env(monkeypatch, tmp_path):
    monkeypatch.setattr(operations, "_OPERATION_STATE_FILE", tmp_path / "operation_state.jsonl")
    monkeypatch.setattr(operations, "_IDEMPOTENCY_TTL_SECONDS", 300)
    monkeypatch.setattr(operations, "check_rate_limit", lambda **kwargs: (True, 0))
    monkeypatch.setattr(operations, "is_admin", lambda user_info: True)
    operations._IDEMPOTENCY_CACHE.clear()


def test_restart_rejected_when_in_progress():
    manager = minecraft_server.ServerManager()
    manager.restart_in_progress = True

    result = asyncio.run(manager.restart_server(source="admin_ui"))

    assert result["success"] is False
    assert result["error_code"] == "restart_in_progress"


def test_restart_rejected_during_cooldown():
    manager = minecraft_server.ServerManager()
    manager.last_restart_completed_at = datetime.now()
    manager.last_restart_source = "admin_ui"

    result = asyncio.run(manager.restart_server(source="staff_ui"))

    assert result["success"] is False
    assert result["error_code"] == "restart_cooldown"
    assert result["retry_after_seconds"] > 0
    assert result["last_restart_source"] == "admin_ui"


def test_restart_sets_cooldown_after_success(monkeypatch):
    manager = minecraft_server.ServerManager()

    async def _fake_sleep(seconds):
        return None

    async def _fake_stop_server(force: bool = False):
        return {"success": True, "message": "stopped"}

    async def _fake_start_server(
        wait_for_ready: bool = False,
        ready_timeout_sec: int = minecraft_server.DEFAULT_READY_TIMEOUT_SEC,
        require_rcon_ready: bool = True,
    ):
        return {"success": True, "message": "started"}

    monkeypatch.setattr(minecraft_server.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(manager, "stop_server", _fake_stop_server)
    monkeypatch.setattr(manager, "start_server", _fake_start_server)

    first = asyncio.run(manager.restart_server(source="admin_ui"))
    second = asyncio.run(manager.restart_server(source="staff_ui"))

    assert first["success"] is True
    assert second["success"] is False
    assert second["error_code"] == "restart_cooldown"
    assert second["last_restart_source"] == "admin_ui"


def test_execute_operation_passes_restart_source(monkeypatch, tmp_path):
    _setup_operation_test_env(monkeypatch, tmp_path)
    captured = {}

    async def _fake_restart_server(**kwargs):
        captured["source"] = kwargs.get("source")
        return {"success": True, "message": "restarted"}

    monkeypatch.setattr(operations.minecraft_server, "restart_server", _fake_restart_server)

    result = asyncio.run(
        operations.execute_operation(
            key="server:restart",
            user_info={"email": "admin@example.com", "name": "Admin"},
            params={"source": "staff_ui"},
            idempotency_key="restart-source-token",
        )
    )

    assert result["success"] is True
    assert captured["source"] == "staff_ui"


def test_reboot_scheduler_skips_when_restart_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(reboot_scheduler, "CONFIG_FILE", tmp_path / "reboot_scheduler_config.json")
    monkeypatch.setattr(reboot_scheduler, "LOG_FILE", tmp_path / "reboot_scheduler_log.json")

    scheduler = reboot_scheduler.RebootScheduler()
    scheduler.status.state = reboot_scheduler.SchedulerState.COUNTDOWN_UPTIME
    scheduler.status.players_online = 0
    token = scheduler._new_restart_token()

    async def _fake_send_command(command: str):
        return {"success": True, "message": "ok"}

    async def _fake_restart_server(**kwargs):
        return {
            "success": False,
            "error": "Restart cooldown active",
            "error_code": "restart_cooldown",
            "retry_after_seconds": 95,
        }

    monkeypatch.setattr(reboot_scheduler.minecraft_server, "send_command", _fake_send_command)
    monkeypatch.setattr(reboot_scheduler.minecraft_server, "restart_server", _fake_restart_server)

    asyncio.run(scheduler._execute_restart("uptime", token=token))

    assert scheduler.status.state == reboot_scheduler.SchedulerState.MONITORING
    assert scheduler.status.error_message is None
    assert scheduler.logs[-1].action == "restart_skipped"
