import pytest

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.core.auth import ADMIN_EMAILS
from app.routers.admin_server import router as admin_server_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/__test/login")
    async def _login(request: Request):
        request.session["user_info"] = {"email": next(iter(ADMIN_EMAILS)), "name": "Admin"}
        return {"ok": True}

    app.include_router(admin_server_router, prefix="/minecraft/admin")
    return app


@pytest.mark.parametrize("cmd", ["stop", "/stop", "op testuser", "deop testuser", "ban-ip 1.2.3.4"])
def test_dangerous_commands_are_blocked(monkeypatch, cmd: str):
    async def _fake_send_command(command: str) -> dict:
        return {"success": True, "response": "ok"}

    from app.services import minecraft_server
    monkeypatch.setattr(minecraft_server, "send_command", _fake_send_command)

    client = TestClient(_make_app())
    client.get("/__test/login")
    resp = client.post("/minecraft/admin/api/minecraft/server/command", json={"command": cmd})
    assert resp.status_code == 403


def test_allowed_command_passes(monkeypatch):
    async def _fake_send_command(command: str) -> dict:
        return {"success": True, "response": "ok"}

    from app.services import minecraft_server
    monkeypatch.setattr(minecraft_server, "send_command", _fake_send_command)

    client = TestClient(_make_app())
    client.get("/__test/login")
    resp = client.post("/minecraft/admin/api/minecraft/server/command", json={"command": "list"})
    assert resp.status_code == 200
    assert resp.json().get("success") is True
