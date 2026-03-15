# -*- coding: utf-8 -*-
"""Admin role enforcement for /admin/* routes.

Two levels:
- admin: can manage users, view dashboard
- super_admin: can also manage platform API keys
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AdminMiddleware(BaseHTTPMiddleware):
    """Require admin or super_admin role for /api/v1/admin/* routes."""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        if not path.startswith("/api/v1/admin"):
            return await call_next(request)

        role = getattr(request.state, "user_role", None)
        if role not in ("admin", "super_admin"):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "admin_required",
                    "message": "此功能需要管理员权限",
                },
            )

        return await call_next(request)


def super_admin_required(request: Request):
    """FastAPI dependency for super_admin-only routes (e.g., API Key management)."""
    role = getattr(request.state, "user_role", None)
    if role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="super_admin_required",
        )


def add_admin_middleware(app):
    """Add admin middleware to the FastAPI app."""
    app.add_middleware(AdminMiddleware)
