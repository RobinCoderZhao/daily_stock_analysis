# -*- coding: utf-8 -*-
"""Daily cron job for signal lifecycle management.

Should be registered in main scheduler (APScheduler or cron).

Runs daily at 16:00 CST (after market close):
1. Fetch current prices for active signals
2. Check stop_loss / take_profit triggers
3. Close expired signals
4. Compute and cache performance summaries
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SignalUpdaterJob:
    """Daily signal update cycle job."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        """Lazy-load DatabaseManager."""
        if self._db is None:
            from src.storage import DatabaseManager
            self._db = DatabaseManager.get_instance()
        return self._db

    def run(self) -> Dict:
        """Execute daily signal update cycle.

        Returns:
            Dict with update results: {updated, triggered_sl, triggered_tp, expired}
        """
        logger.info("Starting daily signal update job")
        results = {
            "updated": 0,
            "triggered_sl": 0,
            "triggered_tp": 0,
            "expired": 0,
            "errors": [],
        }

        try:
            db = self._get_db()
            from src.storage import Signal
            from sqlalchemy import and_

            with db.get_session() as session:
                active_signals = (
                    session.query(Signal)
                    .filter(Signal.status.in_(["pending", "active"]))
                    .all()
                )

                if not active_signals:
                    logger.info("No active signals to update")
                    return results

                logger.info(f"Updating {len(active_signals)} active signals")

                for signal in active_signals:
                    try:
                        self._update_single_signal(signal, session, results)
                    except Exception as exc:
                        results["errors"].append(f"{signal.code}: {exc}")
                        logger.warning("Failed to update signal %s: %s", signal.code, exc)

                session.commit()

        except Exception as exc:
            logger.error("Signal update job failed: %s", exc, exc_info=True)
            results["errors"].append(str(exc))

        logger.info(
            "Signal update complete: updated=%d, SL=%d, TP=%d, expired=%d",
            results["updated"], results["triggered_sl"],
            results["triggered_tp"], results["expired"],
        )
        return results

    def _update_single_signal(self, signal, session, results: Dict) -> None:
        """Update a single signal: fetch price, check triggers, check expiry."""
        # Fetch current price
        current_price = self._fetch_current_price(signal.code)
        if current_price is None:
            return

        signal.current_price = current_price
        results["updated"] += 1

        # Activate pending signals
        if signal.status == "pending":
            signal.status = "active"

        # Calculate unrealised return
        if signal.entry_price and signal.entry_price > 0:
            if signal.direction == "long":
                signal.return_pct = ((current_price - signal.entry_price) / signal.entry_price) * 100
            else:
                signal.return_pct = ((signal.entry_price - current_price) / signal.entry_price) * 100

        # Check stop loss trigger
        if signal.stop_loss and signal.direction == "long" and current_price <= signal.stop_loss:
            signal.status = "closed_sl"
            signal.closed_at = datetime.now()
            results["triggered_sl"] += 1
            logger.info("Signal %s/%s triggered stop loss at %.2f", signal.code, signal.strategy_name, current_price)
            return

        # Check take profit trigger
        if signal.take_profit and signal.direction == "long" and current_price >= signal.take_profit:
            signal.status = "closed_tp"
            signal.closed_at = datetime.now()
            results["triggered_tp"] += 1
            logger.info("Signal %s/%s triggered take profit at %.2f", signal.code, signal.strategy_name, current_price)
            return

        # Check expiry
        if signal.holding_days and signal.created_at:
            expiry_date = signal.created_at + timedelta(days=signal.holding_days)
            if datetime.now() > expiry_date:
                signal.status = "expired"
                signal.closed_at = datetime.now()
                results["expired"] += 1
                logger.info("Signal %s/%s expired after %d days", signal.code, signal.strategy_name, signal.holding_days)

    def _fetch_current_price(self, code: str) -> Optional[float]:
        """Fetch current price for a stock.

        Tries local DB first, then API if available.
        """
        try:
            db = self._get_db()
            from src.storage import StockDaily

            with db.get_session() as session:
                latest = (
                    session.query(StockDaily)
                    .filter(StockDaily.code == code)
                    .order_by(StockDaily.date.desc())
                    .first()
                )
                if latest and latest.close:
                    return float(latest.close)
        except Exception:
            pass

        # Fallback: try data fetcher API
        try:
            from src.data_fetcher import DataFetcher
            from src.config import get_config
            config = get_config()
            fetcher = DataFetcher(config)
            price = fetcher.get_realtime_price(code)
            if price:
                return float(price)
        except Exception:
            pass

        logger.warning("Could not fetch price for %s", code)
        return None
