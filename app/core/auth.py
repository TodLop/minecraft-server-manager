"""
Authentication and authorization utilities for Project Octopus.
Handles admin role checking and route protection.
"""

import os
from typing import Optional
from fastapi import Request, HTTPException

from app.core.config import STAFF_EMAILS

# Admin email whitelist - loaded from environment variable
# Set ADMIN_EMAILS in .env as comma-separated emails
_admin_emails_str = os.getenv("ADMIN_EMAILS", "")
ADMIN_EMAILS = frozenset(
    email.strip() for email in _admin_emails_str.split(",") if email.strip()
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
    return user_info.get("email") in ADMIN_EMAILS


def is_staff(user_info: Optional[dict]) -> bool:
    """Check if user is a staff member (limited permissions)."""
    if not user_info:
        return False
    return user_info.get("email") in STAFF_EMAILS


def is_admin_or_staff(user_info: Optional[dict]) -> bool:
    """Check if user is admin OR staff."""
    return is_admin(user_info) or is_staff(user_info)


def is_admin_request(request: Request) -> bool:
    """Check if current request is from an admin user."""
    user_info = get_current_user(request)
    return is_admin(user_info)


async def require_auth(request: Request) -> dict:
    """
    FastAPI dependency: require authenticated user.
    Raises 401 if not authenticated.
    """
    user_info = get_current_user(request)
    if not user_info:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return user_info


async def require_admin(request: Request) -> dict:
    """
    FastAPI dependency: require admin user.
    Raises 401 if not authenticated, 403 if not admin.
    """
    user_info = await require_auth(request)
    if not is_admin(user_info):
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return user_info


async def require_staff(request: Request) -> dict:
    """
    FastAPI dependency: require staff or admin user.
    Raises 401 if not authenticated, 403 if not staff/admin.
    """
    user_info = await require_auth(request)
    if not is_admin_or_staff(user_info):
        raise HTTPException(
            status_code=403,
            detail="Staff access required"
        )
    return user_info

