# app/routers/admin_rbac.py
"""
RBAC and Staff Settings Management Routes

Extracted from admin.py - handles staff feature visibility
and role-based access control endpoints.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from app.core.auth import require_admin
from app.core.config import STAFF_EMAILS
from app.services import staff_settings as staff_settings_service
from app.services import permissions as permissions_service

router = APIRouter()


# =============================================================================
# Staff Settings Management (Admin Only)
# =============================================================================


@router.get("/api/staff-settings")
async def admin_get_all_staff_settings(user_info: dict = Depends(require_admin)):
    """Get all staff settings (admin only)."""
    settings = staff_settings_service.get_all_staff_settings()
    available_features = staff_settings_service.get_available_features()

    # Include all staff emails even if they don't have custom settings
    staff_with_settings = {s.email for s in settings}
    all_staff = []

    for setting in settings:
        all_staff.append({
            "email": setting.email,
            "hidden_features": setting.hidden_features,
            "updated_at": setting.updated_at,
            "updated_by": setting.updated_by
        })

    # Add staff without custom settings
    for email in STAFF_EMAILS:
        if email.lower() not in staff_with_settings:
            all_staff.append({
                "email": email.lower(),
                "hidden_features": [],
                "updated_at": None,
                "updated_by": None
            })

    return JSONResponse({
        "status": "ok",
        "staff": all_staff,
        "available_features": available_features
    })


@router.get("/api/staff-settings/{staff_email}")
async def admin_get_staff_settings(staff_email: str, user_info: dict = Depends(require_admin)):
    """Get settings for a specific staff member (admin only)."""
    settings = staff_settings_service.get_staff_settings(staff_email)

    return JSONResponse({
        "status": "ok",
        "settings": {
            "email": settings.email,
            "hidden_features": settings.hidden_features,
            "updated_at": settings.updated_at,
            "updated_by": settings.updated_by
        }
    })


@router.put("/api/staff-settings/{staff_email}")
async def admin_update_staff_settings(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Update feature visibility for a staff member (admin only)."""
    body = await request.json()
    hidden_features = body.get("hidden_features", [])
    admin_email = user_info.get("email", "unknown")

    settings = staff_settings_service.update_staff_settings(
        staff_email=staff_email,
        hidden_features=hidden_features,
        admin_email=admin_email
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Settings updated for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features,
                "updated_at": settings.updated_at
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Failed to update settings"
        }, status_code=500)


@router.post("/api/staff-settings/{staff_email}/toggle")
async def admin_toggle_staff_feature(
    staff_email: str,
    request: Request,
    user_info: dict = Depends(require_admin)
):
    """Toggle a single feature for a staff member (admin only)."""
    body = await request.json()
    feature = body.get("feature", "")
    visible = body.get("visible", True)
    admin_email = user_info.get("email", "unknown")

    if not feature:
        return JSONResponse({
            "success": False,
            "error": "Feature is required"
        }, status_code=400)

    settings = staff_settings_service.toggle_feature_for_staff(
        staff_email=staff_email,
        feature=feature,
        visible=visible,
        admin_email=admin_email
    )

    if settings:
        return JSONResponse({
            "success": True,
            "message": f"Feature '{feature}' {'shown' if visible else 'hidden'} for {staff_email}",
            "settings": {
                "email": settings.email,
                "hidden_features": settings.hidden_features
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Invalid feature or failed to update"
        }, status_code=400)


@router.delete("/api/staff-settings/{staff_email}")
async def admin_delete_staff_settings(staff_email: str, user_info: dict = Depends(require_admin)):
    """Reset staff settings to defaults (admin only)."""
    if staff_settings_service.delete_staff_settings(staff_email):
        return JSONResponse({
            "success": True,
            "message": f"Settings reset for {staff_email}"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "No custom settings found"
        }, status_code=404)


# =============================================================================
# RBAC Permission Management (Admin Only)
# =============================================================================

@router.get("/api/rbac/roles")
async def get_rbac_roles(user_info: dict = Depends(require_admin)):
    """List all role presets with descriptions and permissions."""
    roles = {}
    for role_name, role_data in permissions_service.ROLE_PRESETS.items():
        roles[role_name] = {
            "description": role_data["description"],
            "permissions": sorted(role_data["permissions"]),
        }
    return JSONResponse({"status": "ok", "roles": roles})


@router.get("/api/rbac/permissions")
async def get_rbac_permissions(user_info: dict = Depends(require_admin)):
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
async def get_rbac_users(user_info: dict = Depends(require_admin)):
    """Get all staff with roles and effective permissions."""
    rbac_users = permissions_service.get_all_users()
    rbac_emails = {u.email for u in rbac_users}

    users = []
    for user in rbac_users:
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
        })

    # Include staff not yet in RBAC
    for email in STAFF_EMAILS:
        if email.lower() not in rbac_emails:
            users.append({
                "email": email.lower(),
                "role": None,
                "grants": [],
                "revokes": [],
                "effective_permissions": [],
                "visible_modules": [],
                "updated_at": None,
                "updated_by": None,
            })

    return JSONResponse({"status": "ok", "users": users})


@router.put("/api/rbac/users/{email}/role")
async def set_rbac_user_role(email: str, request: Request, user_info: dict = Depends(require_admin)):
    """Assign a role to a staff member."""
    body = await request.json()
    role = body.get("role")  # None to unassign
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
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Invalid role or failed to update"
        }, status_code=400)


@router.post("/api/rbac/users/{email}/grant")
async def grant_rbac_permission(email: str, request: Request, user_info: dict = Depends(require_admin)):
    """Grant an extra permission to a staff member."""
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
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Invalid permission or failed to update"
        }, status_code=400)


@router.post("/api/rbac/users/{email}/revoke")
async def revoke_rbac_permission(email: str, request: Request, user_info: dict = Depends(require_admin)):
    """Revoke a permission from a staff member."""
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
            }
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "Invalid permission or failed to update"
        }, status_code=400)


@router.delete("/api/rbac/users/{email}")
async def reset_rbac_user(email: str, user_info: dict = Depends(require_admin)):
    """Reset a staff member to no-role (deny all)."""
    admin_email = user_info.get("email", "unknown")

    if permissions_service.reset_user(email, admin_email):
        return JSONResponse({
            "success": True,
            "message": f"RBAC settings reset for {email}"
        })
    else:
        return JSONResponse({
            "success": False,
            "error": "No RBAC settings found for this user"
        }, status_code=404)
