# -*- coding: utf-8 -*-
"""Auth middleware: protect /api/v1/* when admin auth or SaaS mode is enabled.

Supports two auth modes:
1. Legacy admin mode: Cookie-based session (ADMIN_AUTH_ENABLED=true)
2. SaaS mode: JWT Bearer token (SAAS_MODE=true)
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth import COOKIE_NAME, is_auth_enabled, verify_session

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/saas-register",
    "/api/v1/auth/status",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/saas-login",
    "/api/v1/payment/webhook/stripe",
    "/api/v1/payment/webhook/wechat",
    "/api/v1/payment/webhook/alipay",
    "/api/v1/payment/plans",
    "/api/health",
    "/health",
    # /docs, /redoc, /openapi.json removed — protected via FastAPI docs_url=None
})


def _path_exempt(path: str) -> bool:
    """Check if path is exempt from auth."""
    normalized = path.rstrip("/") or "/"
    return normalized in EXEMPT_PATHS


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _verify_jwt_bearer(request: Request) -> bool:
    """Verify JWT Bearer token from Authorization header.

    On success, sets request.state.user_id and request.state.user_role.
    Returns True if authenticated, False otherwise.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header[7:]
    try:
        from src.jwt_auth import verify_token
        payload = verify_token(token, expected_type="access")
        if payload is None:
            return False

        # Attach user info to request state for downstream handlers
        request.state.user_id = int(payload["sub"])
        request.state.user_role = payload.get("role", "user")
        return True
    except Exception:
        return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Require valid session or JWT for /api/v1/* when auth is enabled."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ):
        path = request.url.path

        # Skip non-API paths
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        # Skip exempt paths
        if _path_exempt(path):
            return await call_next(request)

        saas_mode = _is_saas_mode()

        if saas_mode:
            # SaaS mode: require JWT Bearer
            if _verify_jwt_bearer(request):
                return await call_next(request)

            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Valid JWT token required",
                },
            )

        # Legacy admin mode: require cookie session
        if not is_auth_enabled():
            return await call_next(request)

        cookie_val = request.cookies.get(COOKIE_NAME)
        if not cookie_val or not verify_session(cookie_val):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Login required",
                },
            )

        return await call_next(request)


def add_auth_middleware(app):
    """Add auth middleware to protect API routes.

    The middleware is always registered; whether auth is enforced is determined
    at request time by is_auth_enabled() / _is_saas_mode() so the decision stays
    consistent across any runtime configuration reload.
    """
    app.add_middleware(AuthMiddleware)
