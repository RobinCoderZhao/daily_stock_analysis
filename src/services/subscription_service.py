# -*- coding: utf-8 -*-
"""Subscription lifecycle management and payment orchestration."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

# Tier configuration: limits and features
TIER_CONFIG = {
    "free": {
        "watchlist_limit": 3,
        "daily_analysis_limit": None,   # Auto-analysis for watchlist (no per-day cap)
        "agent_daily_limit": 0,         # No agent chat
        "trial_days": 7,
        "price_monthly_cents": 0,
        "price_yearly_cents": 0,
        "features": ["basic_analysis"],
    },
    "standard": {
        "watchlist_limit": 20,
        "daily_analysis_limit": None,
        "agent_daily_limit": 10,
        "price_monthly_cents": 19900,   # ¥199/month
        "price_yearly_cents": 199000,   # ¥1990/year (~17% off)
        "features": ["basic_analysis", "agent_chat", "backtest", "signals"],
    },
    "pro": {
        "watchlist_limit": 100,
        "daily_analysis_limit": None,
        "agent_daily_limit": None,      # Unlimited
        "price_monthly_cents": 69900,   # ¥699/month
        "price_yearly_cents": 699000,   # ¥6990/year (~17% off)
        "features": ["basic_analysis", "agent_chat", "backtest", "signals",
                     "export", "api_access"],
    },
}

# Temp credit packs
TEMP_PACKS = {
    "temp_10": {"credits": 10, "price_cents": 10000},    # ¥100 = 10次 (¥10/次)
    "temp_50": {"credits": 50, "price_cents": 45000},     # ¥450 = 50次 (¥9/次)
    "temp_100": {"credits": 100, "price_cents": 80000},   # ¥800 = 100次 (¥8/次)
}


class SubscriptionServiceError(Exception):
    def __init__(self, message: str, code: str = "subscription_error"):
        super().__init__(message)
        self.code = code


class SubscriptionService:
    """Manage subscription lifecycle and payments."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db = db_manager or DatabaseManager.get_instance()

    def get_subscription(self, user_id: int) -> Dict[str, Any]:
        """Get current active subscription for user."""
        from src.models.user import Subscription

        with self._db.get_session() as session:
            sub = (
                session.query(Subscription)
                .filter_by(user_id=user_id, status="active")
                .first()
            )
            if not sub:
                return {"tier": "none", "status": "inactive"}

            return {
                "id": sub.id,
                "tier": sub.tier,
                "status": sub.status,
                "watchlist_limit": sub.watchlist_limit,
                "daily_analysis_limit": sub.daily_analysis_limit,
                "agent_daily_limit": sub.agent_daily_limit,
                "temp_analysis_credits": sub.temp_analysis_credits,
                "expire_at": sub.expire_at.isoformat() if sub.expire_at else None,
                "start_at": sub.start_at.isoformat() if sub.start_at else None,
            }

    def create_checkout(self, user_id: int, plan: str) -> Dict[str, Any]:
        """Create a payment order and return checkout info.

        plan: 'standard_monthly' / 'standard_yearly' / 'pro_monthly' / 'pro_yearly'
              / 'temp_10' / 'temp_50' / 'temp_100'
        """
        from src.models.payment import PaymentOrder

        # Determine amount
        if plan.startswith("temp_"):
            if plan not in TEMP_PACKS:
                raise SubscriptionServiceError(f"Unknown temp pack: {plan}", "invalid_plan")
            amount_cents = TEMP_PACKS[plan]["price_cents"]
        else:
            tier, period = self._parse_plan(plan)
            if tier not in TIER_CONFIG:
                raise SubscriptionServiceError(f"Unknown tier: {tier}", "invalid_plan")
            key = f"price_{period}_cents"
            amount_cents = TIER_CONFIG[tier].get(key, 0)
            if not amount_cents:
                raise SubscriptionServiceError(f"No price for plan: {plan}", "invalid_plan")

        order_no = f"DSA-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        currency = os.environ.get("PAYMENT_CURRENCY", "CNY")

        with self._db.get_session() as session:
            order = PaymentOrder(
                user_id=user_id,
                order_no=order_no,
                plan=plan,
                amount_cents=amount_cents,
                currency=currency,
                status="pending",
            )
            session.add(order)
            session.commit()

            return {
                "order_no": order_no,
                "plan": plan,
                "amount_cents": amount_cents,
                "currency": currency,
            }

    def handle_payment_success(self, order_no: str, provider: str = "stripe",
                                provider_id: str = "") -> None:
        """Called by webhook: activate subscription or add credits."""
        from src.models.payment import PaymentOrder
        from src.models.user import Subscription

        with self._db.get_session() as session:
            order = (
                session.query(PaymentOrder)
                .filter_by(order_no=order_no)
                .first()
            )
            if not order:
                raise SubscriptionServiceError("Order not found", "order_not_found")

            if order.status == "paid":
                logger.info(f"Order {order_no} already processed")
                return

            # Mark order as paid
            order.status = "paid"
            order.paid_at = datetime.now()
            order.payment_provider = provider
            order.payment_provider_id = provider_id

            # Apply the plan
            if order.plan.startswith("temp_"):
                # Add temp credits
                pack = TEMP_PACKS.get(order.plan)
                if pack:
                    sub = (
                        session.query(Subscription)
                        .filter_by(user_id=order.user_id, status="active")
                        .first()
                    )
                    if sub:
                        sub.temp_analysis_credits = (
                            (sub.temp_analysis_credits or 0) + pack["credits"]
                        )
                    logger.info(
                        f"Added {pack['credits']} temp credits to user {order.user_id}"
                    )
            else:
                # Activate or upgrade subscription
                tier, period = self._parse_plan(order.plan)
                config = TIER_CONFIG[tier]

                if period == "monthly":
                    expire_at = datetime.now() + timedelta(days=30)
                else:
                    expire_at = datetime.now() + timedelta(days=365)

                # Deactivate existing subs
                existing = (
                    session.query(Subscription)
                    .filter_by(user_id=order.user_id, status="active")
                    .all()
                )
                for s in existing:
                    s.status = "superseded"

                # Create new subscription
                new_sub = Subscription(
                    user_id=order.user_id,
                    tier=tier,
                    status="active",
                    watchlist_limit=config["watchlist_limit"],
                    daily_analysis_limit=config.get("daily_analysis_limit"),
                    agent_daily_limit=config.get("agent_daily_limit"),
                    start_at=datetime.now(),
                    expire_at=expire_at,
                )
                session.add(new_sub)
                logger.info(
                    f"Activated {tier} subscription for user {order.user_id} "
                    f"until {expire_at}"
                )

            session.commit()

    def cancel_subscription(self, user_id: int) -> bool:
        """Cancel subscription (keeps active until expire_at)."""
        from src.models.user import Subscription

        with self._db.get_session() as session:
            sub = (
                session.query(Subscription)
                .filter_by(user_id=user_id, status="active")
                .first()
            )
            if not sub:
                return False

            sub.status = "cancelled"
            session.commit()
            logger.info(f"Cancelled subscription for user {user_id}")
            return True

    def check_and_expire(self) -> int:
        """Cron job: expire overdue subscriptions. Returns count expired."""
        from src.models.user import Subscription

        with self._db.get_session() as session:
            now = datetime.now()
            expired_subs = (
                session.query(Subscription)
                .filter(
                    Subscription.status == "active",
                    Subscription.expire_at.isnot(None),
                    Subscription.expire_at < now,
                )
                .all()
            )

            count = 0
            for sub in expired_subs:
                sub.status = "expired"
                count += 1

            if count:
                session.commit()
                logger.info(f"Expired {count} subscriptions")

            return count

    def record_usage(self, user_id: int, action: str,
                     stock_code: str = None, tokens_used: int = 0) -> None:
        """Record a usage event for billing/analytics."""
        from src.models.payment import UsageRecord

        with self._db.get_session() as session:
            record = UsageRecord(
                user_id=user_id,
                action=action,
                stock_code=stock_code,
                tokens_used=tokens_used,
            )
            session.add(record)
            session.commit()

    def get_today_usage_count(self, user_id: int, action: str) -> int:
        """Count today's usage for a specific action."""
        from src.models.payment import UsageRecord

        with self._db.get_session() as session:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            count = (
                session.query(UsageRecord)
                .filter(
                    UsageRecord.user_id == user_id,
                    UsageRecord.action == action,
                    UsageRecord.created_at >= today_start,
                )
                .count()
            )
            return count

    def get_plans(self) -> Dict[str, Any]:
        """Get available subscription plans for display."""
        return {
            "tiers": {
                tier: {
                    "watchlist_limit": cfg["watchlist_limit"],
                    "agent_daily_limit": cfg["agent_daily_limit"],
                    "features": cfg["features"],
                    "price_monthly_cents": cfg.get("price_monthly_cents", 0),
                    "price_yearly_cents": cfg.get("price_yearly_cents", 0),
                }
                for tier, cfg in TIER_CONFIG.items()
            },
            "temp_packs": TEMP_PACKS,
        }

    @staticmethod
    def _parse_plan(plan: str):
        """Parse plan string into (tier, period)."""
        parts = plan.rsplit("_", 1)
        if len(parts) != 2 or parts[1] not in ("monthly", "yearly"):
            raise SubscriptionServiceError(f"Invalid plan format: {plan}", "invalid_plan")
        return parts[0], parts[1]
