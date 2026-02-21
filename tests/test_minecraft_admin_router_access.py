import json

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.routers.admin import router as admin_router
from app.services import minecraft_admin_tiers as tiers
from app.services import user_preferences as prefs_service


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
    async def _login(email: str, request: Request):
        request.session["user_info"] = {"email": email, "name": "Test"}
        return {"ok": True}

    app.include_router(admin_router)
    return app


def test_manager_admin_can_access_admin_preferences(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    prefs_file = tmp_path / "user_preferences.json"
    _write_tier_state(tier_file, email=manager_email, active=True)

    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)
    monkeypatch.setattr(prefs_service, "PREFERENCES_FILE", prefs_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    resp = client.get("/minecraft/admin/api/preferences")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_non_manager_non_admin_is_blocked(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    prefs_file = tmp_path / "user_preferences.json"
    _write_tier_state(tier_file, email=manager_email, active=True)

    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)
    monkeypatch.setattr(prefs_service, "PREFERENCES_FILE", prefs_file)

    client = TestClient(_make_app())
    client.get("/__test/login/random-user@example.com")

    resp = client.get("/minecraft/admin/api/preferences")
    assert resp.status_code == 403
