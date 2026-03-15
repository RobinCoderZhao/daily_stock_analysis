# -*- coding: utf-8 -*-
"""Authentication endpoints for Web admin login."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_HOURS_DEFAULT,
    change_password,
    check_rate_limit,
    clear_rate_limit,
    create_session,
    get_client_ip,
    is_auth_enabled,
    is_password_changeable,
    is_password_set,
    record_login_failure,
    set_initial_password,
    verify_password,
    verify_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body. For first-time setup use password + password_confirm."""

    model_config = {"populate_by_name": True}

    password: str = Field(default="", description="Admin password")
    password_confirm: str | None = Field(default=None, alias="passwordConfirm", description="Confirm (first-time)")


class ChangePasswordRequest(BaseModel):
    """Change password request body."""

    model_config = {"populate_by_name": True}

    current_password: str = Field(default="", alias="currentPassword")
    new_password: str = Field(default="", alias="newPassword")
    new_password_confirm: str = Field(default="", alias="newPasswordConfirm")


def _cookie_params(request: Request) -> dict:
    """Build cookie params including Secure based on request."""
    secure = False
    if os.getenv("TRUST_X_FORWARDED_FOR", "false").lower() == "true":
        proto = request.headers.get("X-Forwarded-Proto", "").lower()
        secure = proto == "https"
    else:
        # Check URL scheme when not behind proxy
        secure = request.url.scheme == "https"

    try:
        max_age_hours = int(os.getenv("ADMIN_SESSION_MAX_AGE_HOURS", str(SESSION_MAX_AGE_HOURS_DEFAULT)))
    except ValueError:
        max_age_hours = SESSION_MAX_AGE_HOURS_DEFAULT
    max_age = max_age_hours * 3600

    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
        "max_age": max_age,
    }


@router.get(
    "/status",
    summary="Get auth status",
    description="Returns whether auth is enabled and if the current request is logged in.",
)
async def auth_status(request: Request):
    """Return authEnabled, loggedIn, passwordSet, passwordChangeable without requiring auth."""
    auth_enabled = is_auth_enabled()
    logged_in = False
    if auth_enabled:
        cookie_val = request.cookies.get(COOKIE_NAME)
        logged_in = verify_session(cookie_val) if cookie_val else False
    saas_mode = os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")
    return {
        "authEnabled": auth_enabled,
        "loggedIn": logged_in,
        "passwordSet": is_password_set() if auth_enabled else False,
        "passwordChangeable": is_password_changeable() if auth_enabled else False,
        "saasMode": saas_mode,
    }


@router.post(
    "/login",
    summary="Login or set initial password",
    description="Verify password and set session cookie. If password not set yet, accepts password+passwordConfirm.",
)
async def auth_login(request: Request, body: LoginRequest):
    """Verify password or set initial password, set cookie on success. Returns 401 or 429 on failure."""
    if not is_auth_enabled():
        return JSONResponse(
            status_code=400,
            content={"error": "auth_disabled", "message": "Authentication is not configured"},
        )

    password = (body.password or "").strip()
    if not password:
        return JSONResponse(
            status_code=400,
            content={"error": "password_required", "message": "请输入密码"},
        )

    ip = get_client_ip(request)
    if not check_rate_limit(ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limited",
                "message": "Too many failed attempts. Please try again later.",
            },
        )

    password_set = is_password_set()

    if not password_set:
        # First-time setup: require passwordConfirm
        confirm = (body.password_confirm or "").strip()
        if password != confirm:
            record_login_failure(ip)
            return JSONResponse(
                status_code=400,
                content={"error": "password_mismatch", "message": "Passwords do not match"},
            )
        err = set_initial_password(password)
        if err:
            record_login_failure(ip)
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_password", "message": err},
            )
    else:
        if not verify_password(password):
            record_login_failure(ip)
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_password", "message": "密码错误"},
            )

    clear_rate_limit(ip)
    session_val = create_session()
    if not session_val:
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "Failed to create session"},
        )

    resp = JSONResponse(content={"ok": True})
    params = _cookie_params(request)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=session_val,
        httponly=params["httponly"],
        samesite=params["samesite"],
        secure=params["secure"],
        path=params["path"],
        max_age=params["max_age"],
    )
    return resp


@router.post(
    "/change-password",
    summary="Change password",
    description="Change password. Requires valid session.",
)
async def auth_change_password(body: ChangePasswordRequest):
    """Change password. Requires login."""
    if not is_password_changeable():
        return JSONResponse(
            status_code=400,
            content={"error": "not_changeable", "message": "Password cannot be changed via web"},
        )

    current = (body.current_password or "").strip()
    new_pwd = (body.new_password or "").strip()
    new_confirm = (body.new_password_confirm or "").strip()

    if not current:
        return JSONResponse(
            status_code=400,
            content={"error": "current_required", "message": "请输入当前密码"},
        )
    if new_pwd != new_confirm:
        return JSONResponse(
            status_code=400,
            content={"error": "password_mismatch", "message": "两次输入的新密码不一致"},
        )

    err = change_password(current, new_pwd)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_password", "message": err},
        )
    return Response(status_code=204)


@router.post(
    "/logout",
    summary="Logout",
    description="Clear session cookie.",
)
async def auth_logout(request: Request):
    """Clear session cookie."""
    resp = Response(status_code=204)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


# ============================================================
# SaaS mode endpoints (only active when SAAS_MODE=true)
# ============================================================


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _set_refresh_cookie(response: JSONResponse, refresh_token: str, request: Request = None):
    """Set refresh token as HttpOnly cookie."""
    response.set_cookie(
        key="dsa_refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set True in production with HTTPS
        path="/api/v1/auth",
        max_age=7 * 24 * 3600,  # 7 days
    )


@router.post(
    "/register",
    summary="Register new user (SaaS mode)",
    description="Create a new user account with email and password.",
)
async def auth_register(request: Request):
    """Register a new user. Only available in SaaS mode."""
    if not _is_saas_mode():
        return JSONResponse(
            status_code=400,
            content={"error": "saas_only", "message": "Registration requires SaaS mode"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_body"})

    email = (body.get("email") or "").strip()
    password = (body.get("password") or "").strip()
    nickname = (body.get("nickname") or "").strip() or None

    try:
        from src.services.user_service import UserService, UserServiceError
        service = UserService()
        result = service.register(email=email, password=password, nickname=nickname)

        resp = JSONResponse(content={
            "user_id": result["user_id"],
            "email": result["email"],
            "nickname": result["nickname"],
            "role": result["role"],
            "tier": result["tier"],
            "access_token": result["access_token"],
        })
        _set_refresh_cookie(resp, result["refresh_token"])
        return resp

    except UserServiceError as e:
        status = 409 if e.code == "email_exists" else 400
        return JSONResponse(status_code=status, content={"error": e.code, "message": str(e)})
    except Exception as e:
        logger.exception("Registration error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(e)})


@router.post(
    "/saas-login",
    summary="Login with JWT (SaaS mode)",
    description="Authenticate with email/password and receive JWT tokens.",
)
async def auth_saas_login(request: Request):
    """JWT-based login for SaaS mode."""
    if not _is_saas_mode():
        return JSONResponse(
            status_code=400,
            content={"error": "saas_only", "message": "JWT login requires SaaS mode"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_body"})

    email = (body.get("email") or "").strip()
    password = (body.get("password") or "").strip()

    try:
        from src.services.user_service import UserService, UserServiceError
        service = UserService()
        result = service.login(email=email, password=password)

        resp = JSONResponse(content={
            "user_id": result["user_id"],
            "email": result["email"],
            "nickname": result["nickname"],
            "role": result["role"],
            "tier": result["tier"],
            "access_token": result["access_token"],
        })
        _set_refresh_cookie(resp, result["refresh_token"])
        return resp

    except UserServiceError as e:
        status = 401 if e.code == "auth_failed" else 400
        return JSONResponse(status_code=status, content={"error": e.code, "message": str(e)})
    except Exception as e:
        logger.exception("Login error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(e)})


@router.post(
    "/refresh",
    summary="Refresh access token",
    description="Generate new access token from refresh token cookie.",
)
async def auth_refresh(request: Request):
    """Refresh access token using HttpOnly cookie."""
    if not _is_saas_mode():
        return JSONResponse(
            status_code=400,
            content={"error": "saas_only", "message": "Token refresh requires SaaS mode"},
        )

    refresh = request.cookies.get("dsa_refresh_token")
    if not refresh:
        return JSONResponse(status_code=401, content={"error": "missing_refresh_token"})

    try:
        from src.services.user_service import UserService, UserServiceError
        service = UserService()
        result = service.refresh_token(refresh)

        resp = JSONResponse(content={"access_token": result["access_token"]})
        _set_refresh_cookie(resp, result["refresh_token"])
        return resp

    except UserServiceError as e:
        return JSONResponse(status_code=401, content={"error": e.code, "message": str(e)})


@router.get(
    "/me",
    summary="Get user profile (SaaS mode)",
    description="Return current user profile with subscription info.",
)
async def auth_me(request: Request):
    """Get current user's profile. Requires JWT authentication."""
    if not _is_saas_mode():
        return JSONResponse(
            status_code=400,
            content={"error": "saas_only", "message": "Profile requires SaaS mode"},
        )

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    try:
        from src.services.user_service import UserService, UserServiceError
        service = UserService()
        return service.get_profile(user_id)
    except UserServiceError as e:
        return JSONResponse(status_code=404, content={"error": e.code, "message": str(e)})

