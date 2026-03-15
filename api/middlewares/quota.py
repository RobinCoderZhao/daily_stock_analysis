# -*- coding: utf-8 -*-
"""Subscription quota enforcement middleware.

Checks:
1. Subscription validity (active + not expired)
2. Free trial expiry (7 days from registration)
3. Feature gating (agent chat, backtest, etc.)
4. Agent daily limits
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.services.subscription_service import TIER_CONFIG

logger = logging.getLogger(__name__)

# Endpoint path prefix → required feature
FEATURE_GATES = {
    "/api/v1/agent/chat": "agent_chat",
    "/api/v1/backtest/": "backtest",
    "/api/v1/signals/": "signals",
    "/api/v1/profile/": "basic_analysis",  # Always allowed
}

# Paths that don't need quota check
QUOTA_EXEMPT = frozenset({
    "/api/v1/auth/",
    "/api/v1/payment/",
    "/api/health",
    "/health",
})


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _match_feature(path: str) -> Optional[str]:
    """Match path to a feature gate."""
    for prefix, feature in FEATURE_GATES.items():
        if path.startswith(prefix):
            return feature
    return None


def _is_quota_exempt(path: str) -> bool:
    """Check if path is exempt from quota checks."""
    for exempt in QUOTA_EXEMPT:
        if path.startswith(exempt):
            return True
    return False


class QuotaMiddleware(BaseHTTPMiddleware):
    """Enforce subscription quotas on API requests in SaaS mode."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not _is_saas_mode():
            return await call_next(request)

        path = request.url.path

        # Skip non-API and exempt paths
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        if _is_quota_exempt(path):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return await call_next(request)

        # 1. Check subscription validity
        sub = self._get_active_subscription(user_id)
        if not sub:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "subscription_expired",
                    "message": "您的订阅已过期或不存在，请续费",
                },
            )

        # 2. Free trial expiry
        if sub.tier == "free" and sub.expire_at and datetime.now() > sub.expire_at:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "free_trial_expired",
                    "message": "免费试用已到期，请升级订阅",
                },
            )

        # 3. Feature gating
        required_feature = _match_feature(path)
        tier_config = TIER_CONFIG.get(sub.tier, TIER_CONFIG["free"])
        if required_feature and required_feature not in tier_config.get("features", []):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "feature_not_available",
                    "message": "此功能需要升级至更高会员等级",
                    "required_feature": required_feature,
                    "current_tier": sub.tier,
                },
            )

        # 4. Agent daily limit
        if required_feature == "agent_chat":
            limit = sub.agent_daily_limit
            if limit is not None and limit >= 0:
                from src.services.subscription_service import SubscriptionService
                svc = SubscriptionService()
                used = svc.get_today_usage_count(user_id, "agent_chat")
                if used >= limit:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "agent_daily_limit_reached",
                            "message": f"今日 Agent 对话已达上限（{limit}次），明日重置或升级订阅",
                            "limit": limit,
                            "used": used,
                        },
                    )

        # Attach subscription to request state for downstream use
        request.state.subscription = sub
        return await call_next(request)

    @staticmethod
    def _get_active_subscription(user_id: int):
        """Get active subscription for user."""
        try:
            from src.models.user import Subscription
            from src.storage import DatabaseManager

            db = DatabaseManager.get_instance()
            with db.get_session() as session:
                return (
                    session.query(Subscription)
                    .filter_by(user_id=user_id, status="active")
                    .first()
                )
        except Exception as e:
            logger.error(f"Failed to check subscription for user {user_id}: {e}")
            return None


def add_quota_middleware(app):
    """Add quota middleware to the FastAPI app."""
    app.add_middleware(QuotaMiddleware)
