# -*- coding: utf-8 -*-
"""Pydantic schemas for auth API endpoints."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=6)
    nickname: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class AuthTokenResponse(BaseModel):
    """Response containing JWT tokens and user info."""
    user_id: int
    email: str
    nickname: Optional[str] = None
    role: str
    tier: str
    access_token: str


class ProfileResponse(BaseModel):
    """User profile response."""
    user_id: int
    uuid: str
    email: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    tier: str
    watchlist_limit: int
    expire_at: Optional[str] = None
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    old_password: str
    new_password: str = Field(..., min_length=6)


class RefreshTokenResponse(BaseModel):
    """Access token refresh response."""
    access_token: str
