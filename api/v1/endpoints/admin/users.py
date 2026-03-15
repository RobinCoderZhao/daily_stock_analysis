# -*- coding: utf-8 -*-
"""Admin user management API endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin"])


class UpdateStatusRequest(BaseModel):
    status: str  # active / suspended


class AdjustSubRequest(BaseModel):
    tier: Optional[str] = None  # free / standard / pro
    temp_credits: Optional[int] = None  # Add temp analysis credits
    extend_days: Optional[int] = None  # Extend subscription by N days


@router.get("/")
async def list_users(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
):
    """Paginated user list with search by email/nickname."""
    from src.models.user import User

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        query = session.query(User)
        if search:
            query = query.filter(
                User.email.ilike(f"%{search}%") | User.nickname.ilike(f"%{search}%")
            )

        total = query.count()
        users = (
            query.order_by(User.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "nickname": u.nickname,
                    "role": u.role,
                    "status": u.status,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
        }


@router.get("/{user_id}")
async def get_user_detail(user_id: int):
    """User detail with subscription, usage stats."""
    from src.models.user import User, Subscription
    from src.models.payment import UsageRecord

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return JSONResponse(404, {"error": "user_not_found"})

        sub = (
            session.query(Subscription)
            .filter_by(user_id=user_id, status="active")
            .first()
        )

        # Recent usage count
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_usage = (
            session.query(UsageRecord)
            .filter(UsageRecord.user_id == user_id, UsageRecord.created_at >= today_start)
            .count()
        )

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "nickname": user.nickname,
                "role": user.role,
                "status": user.status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "subscription": {
                "tier": sub.tier if sub else "none",
                "status": sub.status if sub else "inactive",
                "expire_at": sub.expire_at.isoformat() if sub and sub.expire_at else None,
                "temp_credits": sub.temp_analysis_credits if sub else 0,
            } if sub else None,
            "usage_today": today_usage,
        }


@router.put("/{user_id}/status")
async def update_user_status(user_id: int, body: UpdateStatusRequest):
    """Suspend / reactivate user."""
    from src.models.user import User

    if body.status not in ("active", "suspended"):
        return JSONResponse(400, {"error": "invalid_status"})

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return JSONResponse(404, {"error": "user_not_found"})

        user.status = body.status
        session.commit()
        logger.info(f"Admin updated user {user_id} status to {body.status}")
        return {"ok": True, "status": body.status}


@router.put("/{user_id}/subscription")
async def adjust_subscription(user_id: int, body: AdjustSubRequest):
    """Manually adjust subscription tier / credits / expiry."""
    from src.models.user import Subscription
    from src.services.subscription_service import TIER_CONFIG
    from datetime import timedelta

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        sub = (
            session.query(Subscription)
            .filter_by(user_id=user_id, status="active")
            .first()
        )

        if not sub:
            return JSONResponse(404, {"error": "no_active_subscription"})

        changes = []

        if body.tier and body.tier in TIER_CONFIG:
            config = TIER_CONFIG[body.tier]
            sub.tier = body.tier
            sub.watchlist_limit = config["watchlist_limit"]
            sub.agent_daily_limit = config.get("agent_daily_limit")
            changes.append(f"tier={body.tier}")

        if body.temp_credits is not None:
            sub.temp_analysis_credits = (sub.temp_analysis_credits or 0) + body.temp_credits
            changes.append(f"+{body.temp_credits} credits")

        if body.extend_days is not None and body.extend_days > 0:
            if sub.expire_at:
                sub.expire_at = sub.expire_at + timedelta(days=body.extend_days)
            else:
                sub.expire_at = datetime.now() + timedelta(days=body.extend_days)
            changes.append(f"+{body.extend_days} days")

        session.commit()
        logger.info(f"Admin adjusted user {user_id} subscription: {', '.join(changes)}")
        return {"ok": True, "changes": changes}
