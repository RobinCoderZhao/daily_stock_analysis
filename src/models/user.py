# -*- coding: utf-8 -*-
"""User and subscription data models for SaaS multi-tenancy."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Date, Text,
    UniqueConstraint, Index,
)
from src.storage import Base


class User(Base):
    """Platform user account."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True)
    nickname = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    role = Column(String(20), nullable=False, default="user")
    # role: user / admin / super_admin
    status = Column(String(20), nullable=False, default="active")
    # status: active / suspended / deleted
    created_at = Column(DateTime, default=datetime.now, index=True)
    last_login_at = Column(DateTime, nullable=True)
    oauth_provider = Column(String(32), nullable=True)
    oauth_id = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_user_email_status", "email", "status"),
    )


class Subscription(Base):
    """User subscription record."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    tier = Column(String(20), nullable=False, default="free")
    # tier: free / standard / pro
    status = Column(String(20), nullable=False, default="active")
    # status: active / expired / cancelled
    watchlist_limit = Column(Integer, nullable=False, default=3)
    start_at = Column(DateTime, default=datetime.now)
    expire_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("ix_sub_user_status", "user_id", "status"),
    )


class UserWatchlist(Base):
    """User stock watchlist entries."""
    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    group_name = Column(String(50), nullable=False, default="默认分组")
    code = Column(String(10), nullable=False)
    name = Column(String(50), nullable=True)
    market = Column(String(10), nullable=False, default="cn")
    sort_order = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uix_watchlist_user_code"),
        Index("ix_watchlist_user_group", "user_id", "group_name"),
    )
