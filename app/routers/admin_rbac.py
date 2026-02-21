# app/routers/admin_rbac.py
"""
RBAC and staff governance endpoints for Minecraft module.

Owner-only scope:
- Legacy staff feature toggles
- Manager-admin promotion/demotion history
- Owner audit log reads

Manager-admin + owner scope:
- Staff RBAC management (staff subjects only)
"""

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse

from app.core.minecraft_access import require_minecraft_owner, require_minecraft_rbac_manager
from app.core.config import STAFF_EMAILS
from app.services import staff_settings as staff_settings_service
from app.services import permissions as permissions_service
from app.services import minecraft_admin_tiers as admin_tiers

router = APIRouter()


def _subject_type(email: str) -> str:
    return admin_tiers.get_subject_type(email)


def _is_staff_subject(email: str) -> bool:
    return _subject_type(email) == "staff"


def _staff_target_blocked_response() -> JSONResponse:
    return JSONResponse(
        {
            "success": False,
            "error": "Target must be a staff account (owner/manager_admin cannot be modified)",
        },
        status_code=403,
    )


# =============================================================================
# Staff Settings Management (Owner Only)
# =============================================================================


@router.get("/api/staff-settings")
async def admin_get_all_staff_settings(user_info: dict = Depends(require_minecraft_owner)):
    """Get all staff settings for staff subjects only (owner only)."""
    owner_email = user_info.get("email", "unknown")
    admin_tiers.reconcile_admin_tiers(actor=owner_email)

    settings = staff_settings_service.get_all_staff_settings()
    available_features = staff_settings_service.get_available_features()

    # Include staff only; manager_admin/owner are intentionally excluded.
    filtered_settings = [s for s in settings if _is_staff_subject(s.email)]
    staff_with_settings = {s.email for s in filtered_settings}
    all_staff = []

    for setting in filtered_settings:
        all_staff.append({
            "email": setting.email,
            "hidden_features": setting.hidden_features,
            "updated_at": setting.updated_at,
            "updated_by": setting.updated_by,
            "subject_type": _subject_type(setting.email),
        })

    for email in sorted(STAFF_EMAILS):
        if not _is_staff_subject(email):
            continue
        email_l = email.lower()
        if email_l not in staff_with_settings:
            all_staff.append({
                "email": email_l,
                "hidden_features": [],
                "updated_at": None,
                "updated_by": None,
                "subject_type": "staff",
            })

    return JSONResponse({
        "status": "ok",
        "staff": all_staff,
        "available_features": available_features,
    })


@router.get("/api/staff-settings/{staff_email}")
async def admin_get_staff_settings(
    staff_email: str,
    user_info: dict = Depends(require_minecraft_owner),
):
    """Get settings for a specific staff member (owner only)."""
    if not _is_staff_subject(staff_email):
        return JSONResponse(
            {"success": False, "error": "Target must be a staff account"},
            status_code=400,
        )

    settings = staff_settings_service.get_staff_settings(staff_email)
    return JSONResponse({
        "status": "ok",
        "settings": {
            "email": settings.email,
            "hidden_features": settings.hidden_features,
            "updated_at": settings.updated_at,
            "updated_by": settings.updated_by,
            "subject_type": _subject_type(settings.email),
        },
    })


@router.put("/api/staff-settings/{staff_email}")
async def admin_update_staff_settings(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_minecraft_owner),
):
    """Update feature visibility for a staff member (owner only)."""
    if not _is_staff_subject(staff_email):
        return JSONResponse(
            {"success": False, "error": "Target must be a staff account"},
            status_code=400,
        )

    body = await request.json()
    hidden_features = body.get("hidden_features", [])
    admin_email = user_info.get("email", "unknown")

    settings = staff_settings_service.update_staff_settings(
        staff_email=staff_email,
        hidden_features=hidden_features,
        admin_email=admin_email,
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Settings updated for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features,
                "updated_at": settings.updated_at,
            },
        })

    return JSONResponse({"success": False, "error": "Failed to update settings"}, status_code=500)


@router.post("/api/staff-settings/{staff_email}/toggle")
async def admin_toggle_staff_feature(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_minecraft_owner),
):
    """Toggle a single feature for a staff member (owner only)."""
    if not _is_staff_subject(staff_email):
        return JSONResponse(
            {"success": False, "error": "Target must be a staff account"},
            status_code=400,
        )

    body = await request.json()
    feature = body.get("feature", "")
    visible = body.get("visible", True)
    admin_email = user_info.get("email", "unknown")

    if not feature:
        return JSONResponse({"success": False, "error": "Feature is required"}, status_code=400)

    settings = staff_settings_service.toggle_feature_for_staff(
        staff_email=staff_email,
        feature=feature,
        visible=visible,
        admin_email=admin_email,
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Feature '{feature}' {'shown' if visible else 'hidden'} for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features,
            },
        })

    return JSONResponse({"success": False, "error": "Invalid feature or failed to update"}, status_code=400)


@router.delete("/api/staff-settings/{staff_email}")
async def admin_delete_staff_settings(
    staff_email: str,
    user_info: dict = Depends(require_minecraft_owner),
):
    """Reset staff settings to defaults (owner only)."""
    if not _is_staff_subject(staff_email):
        return JSONResponse(
            {"success": False, "error": "Target must be a staff account"},
            status_code=400,
        )

    if staff_settings_service.delete_staff_settings(staff_email):
        return JSONResponse({"success": True, "message": f"Settings reset for {staff_email}"})
    return JSONResponse({"success": False, "error": "No custom settings found"}, status_code=404)


# =============================================================================
# RBAC Permission Management (Manager Admin + Owner)
# =============================================================================


@router.get("/api/rbac/roles")
async def get_rbac_roles(user_info: dict = Depends(require_minecraft_rbac_manager)):
    """List all role presets with descriptions and permissions."""
    roles = {}
    for role_name, role_data in permissions_service.ROLE_PRESETS.items():
        roles[role_name] = {
            "description": role_data["description"],
            "permissions": sorted(role_data["permissions"]),
        }
    return JSONResponse({"status": "ok", "roles": roles})


@router.get("/api/rbac/permissions")
async def get_rbac_permissions(user_info: dict = Depends(require_minecraft_rbac_manager)):
    """Get all permissions with metadata (description, module)."""
    permissions = {}
    for perm in sorted(permissions_service.ALL_PERMISSIONS):
        meta = permissions_service.PERMISSION_METADATA.get(perm, {})
        permissions[perm] = {
            "module": meta.get("module", "unknown"),
            "description": meta.get("description", perm),
        }
    return JSONResponse({"status": "ok", "permissions": permissions})


@router.get("/api/rbac/users")
async def get_rbac_users(user_info: dict = Depends(require_minecraft_rbac_manager)):
    """Get staff-only RBAC users (manager-admin/owner only)."""
    actor_email = user_info.get("email", "unknown")
    admin_tiers.reconcile_admin_tiers(actor=actor_email)

    rbac_users = permissions_service.get_all_users()
    rbac_emails = {u.email for u in rbac_users}

    users = []
    for user in rbac_users:
        subject_type = _subject_type(user.email)
        if subject_type != "staff":
            continue
        effective = sorted(permissions_service.get_effective_permissions(user.email))
        users.append({
            "email": user.email,
            "role": user.role,
            "grants": user.grants,
            "revokes": user.revokes,
            "effective_permissions": effective,
            "visible_modules": permissions_service.get_user_visible_modules(user.email),
            "updated_at": user.updated_at,
            "updated_by": user.updated_by,
            "subject_type": subject_type,
        })

    for email in STAFF_EMAILS:
        email_l = email.lower()
        if _subject_type(email_l) != "staff":
            continue
        if email_l not in rbac_emails:
            users.append({
                "email": email_l,
                "role": None,
                "grants": [],
                "revokes": [],
                "effective_permissions": [],
                "visible_modules": [],
                "updated_at": None,
                "updated_by": None,
                "subject_type": "staff",
            })

    return JSONResponse({"status": "ok", "users": users})


@router.put("/api/rbac/users/{email}/role")
async def set_rbac_user_role(
    email: str,
    request: Request,
    user_info: dict = Depends(require_minecraft_rbac_manager),
):
    """Assign a role to a staff member (manager-admin/owner only)."""
    if _subject_type(email) != "staff":
        return _staff_target_blocked_response()

    body = await request.json()
    role = body.get("role")
    admin_email = user_info.get("email", "unknown")

    result = permissions_service.set_user_role(email, role, admin_email)
    if result:
        effective = sorted(permissions_service.get_effective_permissions(email))
        return JSONResponse({
            "success": True,
            "message": f"Role {'assigned' if role else 'removed'} for {email}",
            "user": {
                "email": result.email,
                "role": result.role,
                "effective_permissions": effective,
                "visible_modules": permissions_service.get_user_visible_modules(email),
                "subject_type": _subject_type(result.email),
            },
        })

    return JSONResponse({"success": False, "error": "Invalid role or failed to update"}, status_code=400)


@router.post("/api/rbac/users/{email}/grant")
async def grant_rbac_permission(
    email: str,
    request: Request,
    user_info: dict = Depends(require_minecraft_rbac_manager),
):
    """Grant an extra permission to a staff member (manager-admin/owner only)."""
    if _subject_type(email) != "staff":
        return _staff_target_blocked_response()

    body = await request.json()
    permission = body.get("permission", "")
    admin_email = user_info.get("email", "unknown")

    result = permissions_service.grant_permission(email, permission, admin_email)
    if result:
        return JSONResponse({
            "success": True,
            "message": f"Granted {permission} to {email}",
            "user": {
                "email": result.email,
                "grants": result.grants,
                "revokes": result.revokes,
                "effective_permissions": sorted(permissions_service.get_effective_permissions(email)),
                "subject_type": _subject_type(result.email),
            },
        })

    return JSONResponse({"success": False, "error": "Invalid permission or failed to update"}, status_code=400)


@router.post("/api/rbac/users/{email}/revoke")
async def revoke_rbac_permission(
    email: str,
    request: Request,
    user_info: dict = Depends(require_minecraft_rbac_manager),
):
    """Revoke a permission from a staff member (manager-admin/owner only)."""
    if _subject_type(email) != "staff":
        return _staff_target_blocked_response()

    body = await request.json()
    permission = body.get("permission", "")
    admin_email = user_info.get("email", "unknown")

    result = permissions_service.revoke_permission(email, permission, admin_email)
    if result:
        return JSONResponse({
            "success": True,
            "message": f"Revoked {permission} from {email}",
            "user": {
                "email": result.email,
                "grants": result.grants,
                "revokes": result.revokes,
                "effective_permissions": sorted(permissions_service.get_effective_permissions(email)),
                "subject_type": _subject_type(result.email),
            },
        })

    return JSONResponse({"success": False, "error": "Invalid permission or failed to update"}, status_code=400)


@router.delete("/api/rbac/users/{email}")
async def reset_rbac_user(email: str, user_info: dict = Depends(require_minecraft_rbac_manager)):
    """Reset a staff member to no-role (manager-admin/owner only)."""
    if _subject_type(email) != "staff":
        return _staff_target_blocked_response()

    admin_email = user_info.get("email", "unknown")
    if permissions_service.reset_user(email, admin_email):
        return JSONResponse({"success": True, "message": f"RBAC settings reset for {email}"})
    return JSONResponse({"success": False, "error": "No RBAC settings found for this user"}, status_code=404)


# =============================================================================
# Manager Admin Governance (Owner Only)
# =============================================================================


@router.get("/api/minecraft/admin-tiers/overview")
async def get_admin_tiers_overview(user_info: dict = Depends(require_minecraft_owner)):
    """Owner overview for manager admin + staff governance."""
    owner_email = user_info.get("email", "unknown")
    admin_tiers.reconcile_admin_tiers(actor=owner_email)
    overview = admin_tiers.get_owner_overview()
    return JSONResponse({"status": "ok", **overview})


@router.post("/api/minecraft/admin-tiers/promote/{email}")
async def promote_to_manager_admin(email: str, user_info: dict = Depends(require_minecraft_owner)):
    """Promote a staff subject to manager admin tracking (owner only)."""
    owner_email = user_info.get("email", "unknown")
    result = admin_tiers.promote_staff_to_manager_admin(email, owner_email)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/api/minecraft/admin-tiers/demote/{email}")
async def demote_to_staff(email: str, user_info: dict = Depends(require_minecraft_owner)):
    """Demote a tracked manager admin and restore previous staff settings."""
    owner_email = user_info.get("email", "unknown")
    result = admin_tiers.demote_manager_admin_to_staff(email, owner_email)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


@router.get("/api/minecraft/admin-audit/logs")
async def get_owner_audit_logs(
    limit: int = Query(default=100, ge=10, le=500),
    user_info: dict = Depends(require_minecraft_owner),
):
    """Owner-only audit log bundle for manager/admin actions."""
    owner_email = user_info.get("email", "unknown")
    admin_tiers.reconcile_admin_tiers(actor=owner_email)
    logs = admin_tiers.get_owner_audit_logs(limit=limit)
    return JSONResponse({"status": "ok", **logs})
