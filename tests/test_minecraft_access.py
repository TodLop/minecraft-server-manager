import json

from fastapi import Depends, FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.core.minecraft_access import require_minecraft_admin, require_minecraft_owner
from app.services import minecraft_admin_tiers as tiers


def _write_tier_state(path, *, email: str, active: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "manager_admins": {
            email: {
                "email": email,
                "active": active,
                "promoted_at": "2026-02-18T00:00:00",
                "promoted_by": "admin@example.com",
                "snapshot": {
                    "role": "viewer",
                    "grants": [],
                    "revokes": [],
                    "hidden_features": [],
                },
                "restored_after_demotion": not active,
                "demoted_at": None,
                "demoted_by": None,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/__test/login/{email}")
    async def _test_login(email: str, request: Request):
        request.session["user_info"] = {"email": email, "name": "Test"}
        return {"ok": True}

    @app.get("/minecraft/admin")
    async def _minecraft_admin_gate(user_info: dict = Depends(require_minecraft_admin)):
        return {"ok": True, "user": user_info.get("email")}

    @app.get("/minecraft/admin/owner")
    async def _minecraft_owner_gate(user_info: dict = Depends(require_minecraft_owner)):
        return {"ok": True, "user": user_info.get("email")}

    return app


def test_manager_admin_email_can_access_minecraft_admin_when_active(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    resp = client.get("/minecraft/admin")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_manager_admin_email_blocked_when_inactive(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=False)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    resp = client.get("/minecraft/admin")
    assert resp.status_code == 403


def test_owner_gate_allows_only_owner(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")
    manager_resp = client.get("/minecraft/admin/owner")
    assert manager_resp.status_code == 403

    client.get("/__test/login/admin@example.com")
    owner_resp = client.get("/minecraft/admin/owner")
    assert owner_resp.status_code == 200
