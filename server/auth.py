"""
Authentication helper for Xerenity backend.

Extracts user context from Supabase JWT tokens sent by the frontend.
Requires SUPABASE_JWT_SECRET in environment variables.

Usage in views:
    from server.auth import get_user_context

    user_ctx = get_user_context(request)
    # user_ctx = {
    #     "user_id": "uuid",
    #     "email": "user@example.com",
    #     "role": "corp_admin",
    #     "company_id": "uuid" | None,
    #     "is_super_admin": bool
    # }
"""

import os
import jwt
import requests
from pathlib import Path

from dotenv import load_dotenv
from server.main_server import XerenityError

# Ensure .env is loaded (Django doesn't load it by default)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("XTY_URL")
SUPABASE_KEY = os.getenv("XTY_TOKEN")


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT token."""
    if not SUPABASE_JWT_SECRET:
        raise XerenityError(
            message="SUPABASE_JWT_SECRET not configured on server",
            code=500,
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise XerenityError(message="Token expired", code=401)
    except jwt.InvalidTokenError as e:
        raise XerenityError(message=f"Invalid token: {e}", code=401)


def _fetch_user_profile(user_id: str) -> dict:
    """
    Fetch user profile from Supabase (role, company_id).
    Uses the service-level COLLECTOR_BEARER or anon key.
    """
    bearer = os.getenv("COLLECTOR_BEARER") or SUPABASE_KEY
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/user_profiles"
        f"?id=eq.{user_id}&select=role,company_id",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {bearer}",
            "Accept-Profile": "xerenity",
        },
    )
    if resp.status_code != 200:
        raise XerenityError(
            message="Failed to fetch user profile",
            code=500,
        )
    data = resp.json()
    if not data:
        raise XerenityError(
            message="User profile not found",
            code=403,
        )
    return data[0]


def get_user_context(request) -> dict:
    """
    Extract and validate user context from a Django request.

    Reads the Authorization header, decodes the Supabase JWT,
    and fetches the user's role and company_id from user_profiles.

    Args:
        request: Django HttpRequest

    Returns:
        dict with user_id, email, role, company_id, is_super_admin

    Raises:
        XerenityError(401) if token is missing or invalid
        XerenityError(403) if user profile not found
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        raise XerenityError(
            message="Authorization header required. Send Bearer <supabase_token>",
            code=401,
        )

    token = auth_header[7:]  # Strip "Bearer "
    payload = _decode_token(token)

    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise XerenityError(message="Token missing user ID (sub)", code=401)

    profile = _fetch_user_profile(user_id)

    return {
        "user_id": user_id,
        "email": email,
        "role": profile.get("role", "lector"),
        "company_id": profile.get("company_id"),
        "is_super_admin": profile.get("role") == "super_admin",
    }
