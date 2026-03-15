# -*- coding: utf-8 -*-
"""User watchlist management with subscription-based limits."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

# Tier → max watchlist stocks
TIER_WATCHLIST_LIMITS = {
    "free": 3,
    "standard": 20,
    "pro": 100,
}


class WatchlistServiceError(Exception):
    """Watchlist operation error."""

    def __init__(self, message: str, code: str = "watchlist_error"):
        super().__init__(message)
        self.code = code


class WatchlistService:
    """CRUD for user watchlists with quota enforcement."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db = db_manager or DatabaseManager.get_instance()

    def add_stock(
        self,
        user_id: int,
        code: str,
        name: str = None,
        group: str = "默认分组",
        market: str = "cn",
    ) -> Dict[str, Any]:
        """Add stock to user's watchlist.

        Validates:
        - Stock code format
        - Uniqueness per user
        - Subscription quota (watchlist_limit)
        """
        code = (code or "").strip().upper()
        if not code:
            raise WatchlistServiceError("Stock code is required", "invalid_code")

        from src.models.user import UserWatchlist, Subscription

        with self._db.get_session() as session:
            # Check quota
            sub = (
                session.query(Subscription)
                .filter_by(user_id=user_id, status="active")
                .first()
            )
            limit = sub.watchlist_limit if sub else TIER_WATCHLIST_LIMITS["free"]

            current_count = (
                session.query(UserWatchlist)
                .filter_by(user_id=user_id)
                .count()
            )
            if current_count >= limit:
                raise WatchlistServiceError(
                    f"Watchlist limit reached ({limit}). Upgrade subscription for more.",
                    "quota_exceeded",
                )

            # Check uniqueness
            existing = (
                session.query(UserWatchlist)
                .filter_by(user_id=user_id, code=code)
                .first()
            )
            if existing:
                raise WatchlistServiceError(
                    f"Stock {code} already in watchlist",
                    "already_exists",
                )

            # Auto-resolve name if not provided
            if not name:
                name = self._resolve_stock_name(code)

            entry = UserWatchlist(
                user_id=user_id,
                code=code,
                name=name,
                group_name=group,
                market=market,
                sort_order=current_count,
                added_at=datetime.now(),
            )
            session.add(entry)
            session.commit()

            logger.info(f"User {user_id} added stock {code} to watchlist")
            return {
                "id": entry.id,
                "code": entry.code,
                "name": entry.name,
                "group": entry.group_name,
                "market": entry.market,
            }

    def remove_stock(self, user_id: int, code: str) -> bool:
        """Remove stock from watchlist."""
        code = (code or "").strip().upper()
        from src.models.user import UserWatchlist

        with self._db.get_session() as session:
            entry = (
                session.query(UserWatchlist)
                .filter_by(user_id=user_id, code=code)
                .first()
            )
            if not entry:
                raise WatchlistServiceError(
                    f"Stock {code} not in watchlist", "not_found"
                )

            session.delete(entry)
            session.commit()
            logger.info(f"User {user_id} removed stock {code} from watchlist")
            return True

    def get_watchlist(
        self, user_id: int, group: str = None
    ) -> List[Dict[str, Any]]:
        """Get user's watchlist, optionally filtered by group."""
        from src.models.user import UserWatchlist

        with self._db.get_session() as session:
            query = session.query(UserWatchlist).filter_by(user_id=user_id)
            if group:
                query = query.filter_by(group_name=group)

            entries = query.order_by(UserWatchlist.sort_order).all()
            return [
                {
                    "id": e.id,
                    "code": e.code,
                    "name": e.name,
                    "group": e.group_name,
                    "market": e.market,
                    "sort_order": e.sort_order,
                    "added_at": e.added_at.isoformat() if e.added_at else None,
                }
                for e in entries
            ]

    def get_groups(self, user_id: int) -> List[str]:
        """Get user's watchlist group names."""
        from src.models.user import UserWatchlist

        with self._db.get_session() as session:
            groups = (
                session.query(UserWatchlist.group_name)
                .filter_by(user_id=user_id)
                .distinct()
                .all()
            )
            return [g for (g,) in groups]

    def reorder(self, user_id: int, code_order: List[str]) -> None:
        """Update sort_order for stocks by given code order."""
        from src.models.user import UserWatchlist

        with self._db.get_session() as session:
            for idx, code in enumerate(code_order):
                entry = (
                    session.query(UserWatchlist)
                    .filter_by(user_id=user_id, code=code.upper())
                    .first()
                )
                if entry:
                    entry.sort_order = idx
            session.commit()

    def get_quota_info(self, user_id: int) -> Dict[str, Any]:
        """Get user's watchlist quota info."""
        from src.models.user import UserWatchlist, Subscription

        with self._db.get_session() as session:
            sub = (
                session.query(Subscription)
                .filter_by(user_id=user_id, status="active")
                .first()
            )
            limit = sub.watchlist_limit if sub else TIER_WATCHLIST_LIMITS["free"]
            used = (
                session.query(UserWatchlist)
                .filter_by(user_id=user_id)
                .count()
            )
            return {
                "limit": limit,
                "used": used,
                "remaining": max(0, limit - used),
                "tier": sub.tier if sub else "free",
            }

    @staticmethod
    def _resolve_stock_name(code: str) -> str:
        """Try to resolve stock name from code. Returns code if not found."""
        try:
            from src.data_provider import DataProvider
            provider = DataProvider()
            info = provider.get_stock_info(code)
            return info.get("name", code) if info else code
        except Exception:
            return code
