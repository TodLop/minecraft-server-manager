import json

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.core import auth as auth_core
from app.routers.staff import router as staff_router
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
    async def _login(email: str, request: Request):
        request.session["user_info"] = {"email": email, "name": "Test User"}
        return {"ok": True}

    app.include_router(staff_router)
    return app


def test_manager_admin_redirects_from_staff_dashboard(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    staff_set = frozenset({manager_email, "staff@example.com"})
    monkeypatch.setattr(auth_core, "STAFF_EMAILS", staff_set)

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    resp = client.get("/minecraft/staff", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/minecraft/admin"


def test_regular_staff_stays_on_staff_dashboard(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    regular_staff = "staff@example.com"
    staff_set = frozenset({manager_email, regular_staff})
    monkeypatch.setattr(auth_core, "STAFF_EMAILS", staff_set)

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{regular_staff}")

    resp = client.get("/minecraft/staff", follow_redirects=False)
    assert resp.status_code == 200
