import json

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.core import config as core_config
from app.routers import admin_rbac
from app.routers.admin import router as admin_router
from app.services import minecraft_admin_tiers as tiers
from app.services import permissions as permissions_service


def _write_tier_state(path, active_emails: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    manager_admins = {}
    for email in active_emails:
        manager_admins[email] = {
            "email": email,
            "active": True,
            "promoted_at": "2026-02-18T00:00:00",
            "promoted_by": "admin@example.com",
            "snapshot": {
                "role": "viewer",
                "grants": [],
                "revokes": [],
                "hidden_features": [],
            },
            "restored_after_demotion": False,
            "demoted_at": None,
            "demoted_by": None,
        }
    payload = {"version": 2, "manager_admins": manager_admins}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/__test/login/{email}")
    async def _login(email: str, request: Request):
        request.session["user_info"] = {"email": email, "name": "Test User"}
        return {"ok": True}

    app.include_router(admin_router)
    return app


def _set_staff_emails(monkeypatch, emails: frozenset[str]) -> None:
    monkeypatch.setattr(core_config, "STAFF_EMAILS", emails)
    monkeypatch.setattr(admin_rbac, "STAFF_EMAILS", emails)
    monkeypatch.setattr(tiers, "STAFF_EMAILS", emails)


def test_manager_admin_can_manage_staff_rbac(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    staff_email = "staff@example.com"

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    rbac_file = tmp_path / "rbac_settings.json"
    _write_tier_state(tier_file, [manager_email])

    _set_staff_emails(monkeypatch, frozenset({staff_email}))
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)
    monkeypatch.setattr(permissions_service, "RBAC_SETTINGS_FILE", rbac_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    roles_resp = client.get("/minecraft/admin/api/rbac/roles")
    assert roles_resp.status_code == 200
    assert roles_resp.json()["status"] == "ok"

    set_role_resp = client.put(
        f"/minecraft/admin/api/rbac/users/{staff_email}/role",
        json={"role": "viewer"},
    )
    assert set_role_resp.status_code == 200
    assert set_role_resp.json()["success"] is True

    grant_resp = client.post(
        f"/minecraft/admin/api/rbac/users/{staff_email}/grant",
        json={"permission": "plugins:view"},
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["success"] is True


def test_owner_still_can_manage_staff_rbac(monkeypatch, tmp_path):
    staff_email = "staff@example.com"

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    rbac_file = tmp_path / "rbac_settings.json"
    _write_tier_state(tier_file, ["manager@example.com"])

    _set_staff_emails(monkeypatch, frozenset({staff_email}))
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)
    monkeypatch.setattr(permissions_service, "RBAC_SETTINGS_FILE", rbac_file)

    client = TestClient(_make_app())
    client.get("/__test/login/admin@example.com")

    roles_resp = client.get("/minecraft/admin/api/rbac/roles")
    assert roles_resp.status_code == 200

    set_role_resp = client.put(
        f"/minecraft/admin/api/rbac/users/{staff_email}/role",
        json={"role": "viewer"},
    )
    assert set_role_resp.status_code == 200
    assert set_role_resp.json()["success"] is True


def test_manager_admin_cannot_modify_owner_or_other_manager(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    other_manager = "manager2@example.com"

    tier_file = tmp_path / "minecraft_admin_tiers.json"
    rbac_file = tmp_path / "rbac_settings.json"
    _write_tier_state(tier_file, [manager_email, other_manager])

    _set_staff_emails(monkeypatch, frozenset({"staff@example.com"}))
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)
    monkeypatch.setattr(permissions_service, "RBAC_SETTINGS_FILE", rbac_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    owner_resp = client.put(
        "/minecraft/admin/api/rbac/users/admin@example.com/role",
        json={"role": "viewer"},
    )
    assert owner_resp.status_code == 403
    assert "owner/manager_admin" in owner_resp.json()["error"]

    manager_resp = client.put(
        f"/minecraft/admin/api/rbac/users/{other_manager}/role",
        json={"role": "viewer"},
    )
    assert manager_resp.status_code == 403
    assert "owner/manager_admin" in manager_resp.json()["error"]


def test_manager_admin_cannot_use_owner_only_admin_tier_endpoints(monkeypatch, tmp_path):
    manager_email = "manager@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, [manager_email])

    _set_staff_emails(monkeypatch, frozenset({"staff@example.com"}))
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{manager_email}")

    promote_resp = client.post("/minecraft/admin/api/minecraft/admin-tiers/promote/staff@example.com")
    assert promote_resp.status_code == 403

    audit_resp = client.get("/minecraft/admin/api/minecraft/admin-audit/logs")
    assert audit_resp.status_code == 403


def test_regular_staff_cannot_access_rbac_admin_endpoints(monkeypatch, tmp_path):
    staff_email = "staff@example.com"
    tier_file = tmp_path / "minecraft_admin_tiers.json"
    _write_tier_state(tier_file, ["manager@example.com"])

    _set_staff_emails(monkeypatch, frozenset({staff_email}))
    monkeypatch.setattr(tiers, "TIER_STATE_FILE", tier_file)

    client = TestClient(_make_app())
    client.get(f"/__test/login/{staff_email}")

    roles_resp = client.get("/minecraft/admin/api/rbac/roles")
    assert roles_resp.status_code == 403
