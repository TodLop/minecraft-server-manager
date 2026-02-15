"""Authentication and authorization utilities."""

import os
from typing import Optional

from fastapi import HTTPException, Request

from app.core.config import STAFF_EMAILS
from app.services import permissions as permissions_service

_admin_emails = os.getenv("ADMIN_EMAILS", "admin@example.com")
ADMIN_EMAILS = frozenset(
    email.strip().lower() for email in _admin_emails.split(",") if email.strip()
)


def get_current_user(request: Request) -> Optional[dict]:
    """Extract user info from session."""
    return request.session.get("user_info")


def is_authenticated(request: Request) -> bool:
    """Check if user is logged in."""
    return request.session.get("user_info") is not None


def is_admin(user_info: Optional[dict]) -> bool:
    """Check if user has admin privileges."""
    if not user_info:
        return False
    return user_info.get("email", "").lower() in ADMIN_EMAILS


def is_staff(user_info: Optional[dict]) -> bool:
    """Check if user is a staff member."""
    if not user_info:
        return False
    return user_info.get("email", "").lower() in STAFF_EMAILS


def is_admin_or_staff(user_info: Optional[dict]) -> bool:
    """Check if user is admin OR staff."""
    return is_admin(user_info) or is_staff(user_info)


def is_admin_request(request: Request) -> bool:
    """Check if current request is from an admin user."""
    user_info = get_current_user(request)
    return is_admin(user_info)


async def require_auth(request: Request) -> dict:
    """Require authenticated user."""
    user_info = get_current_user(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_info


async def require_admin(request: Request) -> dict:
    """Require admin user."""
    user_info = await require_auth(request)
    if not is_admin(user_info):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_info


async def require_staff(request: Request) -> dict:
    """Require staff or admin user."""
    user_info = await require_auth(request)
    if not is_admin_or_staff(user_info):
        raise HTTPException(status_code=403, detail="Staff access required")
    return user_info


def require_permission(permission: str):
    """FastAPI dependency factory for RBAC permissions."""

    async def dependency(request: Request) -> dict:
        user_info = await require_staff(request)
        if is_admin(user_info):
            return user_info

        email = user_info.get("email", "").lower()
        if not permissions_service.has_permission(email, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user_info

    return dependency
