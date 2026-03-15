# -*- coding: utf-8 -*-
"""Admin dashboard API endpoints — platform metrics and analytics."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin"])


@router.get("/overview")
async def get_overview():
    """Key metrics: total users, active today, revenue, etc."""
    from src.models.user import User, Subscription
    from src.models.payment import PaymentOrder, UsageRecord

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        total_users = session.query(User).count()

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        active_today = (
            session.query(UsageRecord.user_id)
            .filter(UsageRecord.created_at >= today_start)
            .distinct()
            .count()
        )

        active_subs = (
            session.query(Subscription)
            .filter_by(status="active")
            .count()
        )

        # Revenue this month
        month_start = today_start.replace(day=1)
        monthly_revenue = 0
        paid_orders = (
            session.query(PaymentOrder)
            .filter(
                PaymentOrder.status == "paid",
                PaymentOrder.paid_at >= month_start,
            )
            .all()
        )
        for order in paid_orders:
            monthly_revenue += order.amount_cents

        # Today's usage
        today_usage = (
            session.query(UsageRecord)
            .filter(UsageRecord.created_at >= today_start)
            .count()
        )

        return {
            "total_users": total_users,
            "active_today": active_today,
            "active_subscriptions": active_subs,
            "monthly_revenue_cents": monthly_revenue,
            "today_usage": today_usage,
        }


@router.get("/user-growth")
async def user_growth(days: int = 30):
    """User registration trend (daily counts)."""
    from src.models.user import User
    from sqlalchemy import func

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        # Group registrations by date
        results = (
            session.query(
                func.date(User.created_at).label("date"),
                func.count(User.id).label("count"),
            )
            .filter(User.created_at >= start_date)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
            .all()
        )

        return {
            "period_days": days,
            "data": [
                {"date": str(r.date), "registrations": r.count}
                for r in results
            ],
        }


@router.get("/usage-stats")
async def usage_stats(days: int = 30):
    """Analysis count, agent chat count by day."""
    from src.models.payment import UsageRecord
    from sqlalchemy import func

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        results = (
            session.query(
                func.date(UsageRecord.created_at).label("date"),
                UsageRecord.action,
                func.count(UsageRecord.id).label("count"),
            )
            .filter(UsageRecord.created_at >= start_date)
            .group_by(func.date(UsageRecord.created_at), UsageRecord.action)
            .order_by(func.date(UsageRecord.created_at))
            .all()
        )

        return {
            "period_days": days,
            "data": [
                {"date": str(r.date), "action": r.action, "count": r.count}
                for r in results
            ],
        }


@router.get("/revenue")
async def revenue_stats(days: int = 30):
    """Payment revenue by day, by plan."""
    from src.models.payment import PaymentOrder
    from sqlalchemy import func

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        results = (
            session.query(
                func.date(PaymentOrder.paid_at).label("date"),
                PaymentOrder.plan,
                func.sum(PaymentOrder.amount_cents).label("total_cents"),
                func.count(PaymentOrder.id).label("order_count"),
            )
            .filter(
                PaymentOrder.status == "paid",
                PaymentOrder.paid_at >= start_date,
            )
            .group_by(func.date(PaymentOrder.paid_at), PaymentOrder.plan)
            .order_by(func.date(PaymentOrder.paid_at))
            .all()
        )

        return {
            "period_days": days,
            "data": [
                {
                    "date": str(r.date),
                    "plan": r.plan,
                    "total_cents": r.total_cents,
                    "order_count": r.order_count,
                }
                for r in results
            ],
        }


@router.get("/llm-cost")
async def llm_cost_stats(days: int = 30):
    """LLM token usage and estimated cost by action type."""
    from src.models.payment import UsageRecord
    from sqlalchemy import func

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        results = (
            session.query(
                UsageRecord.action,
                func.sum(UsageRecord.tokens_used).label("total_tokens"),
                func.count(UsageRecord.id).label("call_count"),
            )
            .filter(UsageRecord.created_at >= start_date)
            .group_by(UsageRecord.action)
            .all()
        )

        return {
            "period_days": days,
            "data": [
                {
                    "action": r.action,
                    "total_tokens": r.total_tokens or 0,
                    "call_count": r.call_count,
                }
                for r in results
            ],
        }
