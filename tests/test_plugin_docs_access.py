import json

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.core import auth as auth_core
from app.routers.plugin_docs import router as plugin_docs_router
from app.services import minecraft_admin_tiers as tiers
from app.services import permissions as permissions_service
from app.services import plugin_docs as plugin_docs_service
from app.services import plugin_notifications


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

    app.include_router(plugin_docs_router)
    return app


def test_manager_admin_can_view_and_edit_plugin_docs(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    monkeypatch.setattr(auth_core, "STAFF_EMAILS", frozenset({"staff@example.com"}))

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email=manager_email, active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    monkeypatch.setattr(permissions_service, "has_permission", lambda _email, _perm: False)
    monkeypatch.setattr(plugin_docs_service, "get_all_plugins", lambda: {})
    monkeypatch.setattr(
        plugin_docs_service,
        "update_plugin_doc",
        lambda **kwargs: {
            "plugin_id": kwargs["plugin_id"],
            "summary": kwargs.get("summary", ""),
            "description": kwargs.get("description", ""),
        },
    )
    monkeypatch.setattr(plugin_notifications, "create_notification", lambda **_kwargs: None)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    view_resp = client.get("/minecraft/plugins/api/docs")
    assert view_resp.status_code == 200
    assert view_resp.json()["status"] == "ok"

    edit_resp = client.put("/minecraft/plugins/api/docs/test", json={"summary": "hello"})
    assert edit_resp.status_code == 200
    assert edit_resp.json()["status"] == "ok"


def test_regular_staff_needs_plugins_view_permission(monkeypatch, tmp_path):
    staff_email = "staff@example.com"
    monkeypatch.setattr(auth_core, "STAFF_EMAILS", frozenset({staff_email}))

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email="manager@example.com", active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    monkeypatch.setattr(permissions_service, "has_permission", lambda _email, _perm: False)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{staff_email}")

    resp = client.get("/minecraft/plugins/api/docs")
    assert resp.status_code == 403
    assert "plugins:view" in resp.json()["detail"]


def test_regular_staff_with_permission_cannot_edit_docs(monkeypatch, tmp_path):
    staff_email = "staff@example.com"
    monkeypatch.setattr(auth_core, "STAFF_EMAILS", frozenset({staff_email}))

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, email="manager@example.com", active=True)
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    monkeypatch.setattr(permissions_service, "has_permission", lambda _email, _perm: True)
    monkeypatch.setattr(plugin_docs_service, "get_all_plugins", lambda: {})

    client = TestClient(_make_app())
    client.get(f"/__test/login/{staff_email}")

    view_resp = client.get("/minecraft/plugins/api/docs")
    assert view_resp.status_code == 200
    assert view_resp.json()["status"] == "ok"

    edit_resp = client.put("/minecraft/plugins/api/docs/test", json={"summary": "nope"})
    assert edit_resp.status_code == 403
