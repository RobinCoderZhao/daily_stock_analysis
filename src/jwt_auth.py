# -*- coding: utf-8 -*-
"""JWT token generation and verification.

Uses PyJWT with HS256 algorithm. Secret key from JWT_SECRET_KEY env var.
In self-hosted mode (SAAS_MODE=false), this module is not used.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

_jwt_module = None


def _get_jwt():
    """Lazy import PyJWT to avoid hard dependency when not in SaaS mode."""
    global _jwt_module
    if _jwt_module is None:
        try:
            import jwt
            _jwt_module = jwt
        except ImportError:
            raise ImportError(
                "PyJWT is required for SaaS mode. Install with: pip install PyJWT"
            )
    return _jwt_module


def _get_secret() -> str:
    """Get JWT signing secret from environment."""
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        # Auto-generate a secret for development (warn user)
        secret = secrets.token_hex(32)
        os.environ["JWT_SECRET_KEY"] = secret
        logger.warning(
            "JWT_SECRET_KEY not set — auto-generated ephemeral key. "
            "Set JWT_SECRET_KEY in .env for production."
        )
    return secret


def create_access_token(user_id: int, role: str) -> str:
    """Create short-lived access token (15 minutes)."""
    jwt = _get_jwt()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def create_refresh_token(user_id: int) -> str:
    """Create long-lived refresh token (7 days, stored in HttpOnly cookie)."""
    jwt = _get_jwt()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def verify_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token.

    Returns payload dict on success, None on any failure
    (expired, invalid signature, wrong type, etc.).
    """
    jwt = _get_jwt()
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        if payload.get("type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
