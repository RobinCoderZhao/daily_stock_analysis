# -*- coding: utf-8 -*-
"""Service for live signal lifecycle management.

Handles:
1. Creating signals from analysis reports
2. Updating active signal prices
3. Checking stop_loss / take_profit triggers
4. Closing expired signals
5. Providing signal summaries
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from src.repositories.strategy_backtest_repo import SignalRepository
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class SignalService:
    """Manage signal lifecycle."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()
        self.repo = SignalRepository(self.db)

    def create_signal_from_report(
        self,
        *,
        analysis_history_id: int,
        code: str,
        stock_name: str = "",
        strategy_name: str = "",
        direction: str = "long",
        entry_price: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        position_pct: Optional[float] = None,
        confidence: Optional[float] = None,
        holding_days: int = 10,
    ) -> Optional[int]:
        """Create a signal from an analysis report.

        Returns:
            Signal ID if created, None on error.
        """
        try:
            expire = date.today() + timedelta(days=holding_days)
            signal_id = self.repo.create_signal({
                "analysis_history_id": analysis_history_id,
                "code": code,
                "stock_name": stock_name,
                "strategy_name": strategy_name,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "position_pct": position_pct,
                "confidence": confidence,
                "status": "active",
                "current_price": entry_price,
                "return_pct": 0.0,
                "holding_days": holding_days,
                "expire_date": expire,
            })
            logger.info(
                "Created signal #%d for %s (%s) at entry=%.2f",
                signal_id, code, strategy_name, entry_price,
            )
            return signal_id
        except Exception as exc:
            logger.error("Failed to create signal: %s", exc)
            return None

    def update_active_signals(self) -> Dict[str, int]:
        """Daily job: update prices, check triggers, close expired.

        Returns:
            Dict with counts of different actions taken.
        """
        active_data = self.repo.get_active_signals()
        signals = active_data.get("items", [])

        stats = {"updated": 0, "triggered_sl": 0, "triggered_tp": 0, "expired": 0}

        for sig in signals:
            try:
                current_price = self._fetch_current_price(sig["code"])
                if current_price is None or current_price <= 0:
                    continue

                updates: Dict[str, Any] = {"current_price": current_price}

                entry = sig.get("entry_price", 0)
                if entry > 0:
                    updates["return_pct"] = round((current_price - entry) / entry * 100, 4)

                # Check stop loss
                sl = sig.get("stop_loss")
                if sl and current_price <= sl:
                    updates["status"] = "closed_sl"
                    updates["closed_at"] = datetime.now()
                    stats["triggered_sl"] += 1
                    logger.info(
                        "Signal #%d hit stop loss: price=%.2f <= sl=%.2f",
                        sig["id"], current_price, sl,
                    )

                # Check take profit
                tp = sig.get("take_profit")
                if tp and current_price >= tp and updates.get("status") != "closed_sl":
                    updates["status"] = "closed_tp"
                    updates["closed_at"] = datetime.now()
                    stats["triggered_tp"] += 1
                    logger.info(
                        "Signal #%d hit take profit: price=%.2f >= tp=%.2f",
                        sig["id"], current_price, tp,
                    )

                # Check expiry
                expire = sig.get("expire_date")
                if expire and updates.get("status") not in ("closed_sl", "closed_tp"):
                    try:
                        expire_date = (
                            date.fromisoformat(expire) if isinstance(expire, str) else expire
                        )
                        if date.today() >= expire_date:
                            updates["status"] = "expired"
                            updates["closed_at"] = datetime.now()
                            stats["expired"] += 1
                    except (ValueError, TypeError):
                        pass

                self.repo.update_signal(sig["id"], updates)
                stats["updated"] += 1

            except Exception as exc:
                logger.warning("Error updating signal #%d: %s", sig.get("id", 0), exc)

        return stats

    def close_expired_signals(self) -> int:
        """Close signals past their holding_days."""
        active_data = self.repo.get_active_signals(page=1, limit=1000)
        signals = active_data.get("items", [])
        count = 0
        for sig in signals:
            expire = sig.get("expire_date")
            if not expire:
                continue
            try:
                expire_date = (
                    date.fromisoformat(expire) if isinstance(expire, str) else expire
                )
                if date.today() >= expire_date:
                    self.repo.update_signal(sig["id"], {
                        "status": "expired",
                        "closed_at": datetime.now(),
                    })
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def get_active_signals(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get paginated active signals."""
        return self.repo.get_active_signals(page=page, limit=limit)

    def get_all_signals(
        self,
        status: Optional[str] = None,
        code: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get all signals with optional filters."""
        return self.repo.get_all_signals(
            status=status, code=code, page=page, limit=limit,
        )

    def get_signal_by_id(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """Get signal detail."""
        return self.repo.get_signal_by_id(signal_id)

    def get_signal_summary(self) -> Dict[str, Any]:
        """Get aggregated signal performance summary."""
        return self.repo.get_signal_summary()

    def close_signal(self, signal_id: int) -> bool:
        """Manually close a signal."""
        return self.repo.update_signal(signal_id, {
            "status": "cancelled",
            "closed_at": datetime.now(),
        })

    def _fetch_current_price(self, code: str) -> Optional[float]:
        """Fetch current price for a stock."""
        try:
            from src.data_fetcher import DataFetcher
            from src.config import get_config

            config = get_config()
            fetcher = DataFetcher(config)
            quote = fetcher.get_realtime_quote(code)
            if quote and "current_price" in quote:
                return float(quote["current_price"])
        except Exception as exc:
            logger.debug("Failed to fetch price for %s: %s", code, exc)
        return None
