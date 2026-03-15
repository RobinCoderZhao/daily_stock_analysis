# -*- coding: utf-8 -*-
"""User registration, login, and profile management service."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.jwt_auth import create_access_token, create_refresh_token, verify_token

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 100_000
MIN_PASSWORD_LEN = 6
FREE_TRIAL_DAYS = 7
FREE_WATCHLIST_LIMIT = 3

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class UserServiceError(Exception):
    """Base exception for user service errors."""

    def __init__(self, message: str, code: str = "user_error"):
        super().__init__(message)
        self.code = code


def _hash_password(password: str) -> str:
    """Hash password with PBKDF2-SHA256. Returns 'salt:hash' hex string."""
    salt = secrets.token_bytes(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}:{pw_hash.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify password against stored 'salt:hash' string."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
        )
        return secrets.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


class UserService:
    """Manage user lifecycle: registration, authentication, profile."""

    def __init__(self, db_manager=None):
        from src.storage import DatabaseManager
        self._db = db_manager or DatabaseManager.get_instance()

    def register(self, email: str, password: str, nickname: str = None) -> Dict[str, Any]:
        """Register a new user with email + password.

        Creates user record with free subscription (7-day trial).
        Returns user info + JWT tokens.
        """
        # Validate email format
        if not email or not EMAIL_REGEX.match(email):
            raise UserServiceError("Invalid email format", "invalid_email")

        # Validate password length
        if not password or len(password) < MIN_PASSWORD_LEN:
            raise UserServiceError(
                f"Password must be at least {MIN_PASSWORD_LEN} characters",
                "weak_password",
            )

        from src.models.user import User, Subscription

        with self._db.get_session() as session:
            # Check email uniqueness
            existing = session.query(User).filter_by(email=email).first()
            if existing:
                raise UserServiceError("Email already registered", "email_exists")

            # Create user
            user = User(
                uuid=str(uuid.uuid4()),
                email=email,
                nickname=nickname or email.split("@")[0],
                password_hash=_hash_password(password),
                role="user",
                status="active",
            )
            session.add(user)
            session.flush()  # Get user.id

            # Create free subscription with 7-day trial
            subscription = Subscription(
                user_id=user.id,
                tier="free",
                status="active",
                watchlist_limit=FREE_WATCHLIST_LIMIT,
                start_at=datetime.now(),
                expire_at=datetime.now() + timedelta(days=FREE_TRIAL_DAYS),
            )
            session.add(subscription)
            session.commit()

            logger.info(f"New user registered: id={user.id}, email={email}")

            # Generate JWT tokens
            access_token = create_access_token(user.id, user.role)
            refresh_token = create_refresh_token(user.id)

            return {
                "user_id": user.id,
                "uuid": user.uuid,
                "email": user.email,
                "nickname": user.nickname,
                "role": user.role,
                "tier": subscription.tier,
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return JWT tokens."""
        from src.models.user import User, Subscription

        with self._db.get_session() as session:
            user = session.query(User).filter_by(email=email).first()
            if not user:
                raise UserServiceError("Invalid email or password", "auth_failed")

            if user.status != "active":
                raise UserServiceError(
                    f"Account is {user.status}", "account_inactive"
                )

            if not _verify_password(password, user.password_hash):
                raise UserServiceError("Invalid email or password", "auth_failed")

            # Update last login
            user.last_login_at = datetime.now()
            session.commit()

            # Get subscription
            sub = (
                session.query(Subscription)
                .filter_by(user_id=user.id, status="active")
                .first()
            )

            access_token = create_access_token(user.id, user.role)
            refresh_token = create_refresh_token(user.id)

            return {
                "user_id": user.id,
                "uuid": user.uuid,
                "email": user.email,
                "nickname": user.nickname,
                "role": user.role,
                "tier": sub.tier if sub else "free",
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

    def refresh_token(self, refresh_token_str: str) -> Dict[str, Any]:
        """Generate new access token from valid refresh token."""
        payload = verify_token(refresh_token_str, expected_type="refresh")
        if payload is None:
            raise UserServiceError("Invalid or expired refresh token", "invalid_token")

        user_id = int(payload["sub"])
        from src.models.user import User

        with self._db.get_session() as session:
            user = session.query(User).filter_by(id=user_id, status="active").first()
            if not user:
                raise UserServiceError("User not found or inactive", "user_not_found")

            new_access = create_access_token(user.id, user.role)
            new_refresh = create_refresh_token(user.id)

            return {
                "access_token": new_access,
                "refresh_token": new_refresh,
            }

    def get_profile(self, user_id: int) -> Dict[str, Any]:
        """Return user profile with subscription info."""
        from src.models.user import User, Subscription

        with self._db.get_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                raise UserServiceError("User not found", "user_not_found")

            sub = (
                session.query(Subscription)
                .filter_by(user_id=user.id, status="active")
                .first()
            )

            return {
                "user_id": user.id,
                "uuid": user.uuid,
                "email": user.email,
                "nickname": user.nickname,
                "avatar_url": user.avatar_url,
                "role": user.role,
                "tier": sub.tier if sub else "free",
                "watchlist_limit": sub.watchlist_limit if sub else FREE_WATCHLIST_LIMIT,
                "expire_at": sub.expire_at.isoformat() if sub and sub.expire_at else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }

    def change_password(
        self, user_id: int, old_password: str, new_password: str
    ) -> bool:
        """Change password after verifying old password."""
        if not new_password or len(new_password) < MIN_PASSWORD_LEN:
            raise UserServiceError(
                f"New password must be at least {MIN_PASSWORD_LEN} characters",
                "weak_password",
            )

        from src.models.user import User

        with self._db.get_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                raise UserServiceError("User not found", "user_not_found")

            if not _verify_password(old_password, user.password_hash):
                raise UserServiceError("Current password is incorrect", "auth_failed")

            user.password_hash = _hash_password(new_password)
            session.commit()
            logger.info(f"Password changed for user {user_id}")
            return True
