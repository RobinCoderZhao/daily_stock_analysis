# -*- coding: utf-8 -*-
"""Orchestrate daily analysis with cross-user deduplication.

In SaaS mode, the scheduler:
1. Collects all active users' watchlists → deduplicated stock set
2. For each unique stock, checks if already analyzed today
3. Only runs LLM analysis for stocks not yet analyzed
4. Results are stored globally and shared across users
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class AnalysisScheduler:
    """Collect all users' watchlists → deduplicate → analyze each stock once."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db = db_manager or DatabaseManager.get_instance()

    def run_daily_analysis(self) -> Dict[str, Any]:
        """Main entry point for daily scheduled analysis.

        Returns:
            Summary dict: {analyzed: N, skipped: N, failed: N, stocks: [...]}
        """
        today = date.today()
        codes = self._get_active_stock_codes()
        if not codes:
            logger.info("No active stock codes to analyze.")
            return {"analyzed": 0, "skipped": 0, "failed": 0, "stocks": []}

        logger.info(
            f"SaaS daily analysis: {len(codes)} unique stocks from all active users."
        )

        analyzed = 0
        skipped = 0
        failed = 0
        results = []

        for code in codes:
            status = self._get_or_create_daily_record(code, today)

            if status == "completed":
                skipped += 1
                continue
            elif status == "analyzing":
                # Another worker is handling it
                skipped += 1
                continue

            # status is 'pending' or 'failed' — attempt analysis
            success = self._analyze_stock(code, today)
            if success:
                analyzed += 1
                results.append(code)
            else:
                failed += 1

        summary = {
            "analyzed": analyzed,
            "skipped": skipped,
            "failed": failed,
            "stocks": results,
            "date": today.isoformat(),
        }
        logger.info(f"Daily analysis complete: {summary}")
        return summary

    def _get_active_stock_codes(self) -> List[str]:
        """Get deduplicated list of stock codes from all active users.

        Active user = status='active' AND subscription not expired.
        Free users: only within 7-day trial period.
        """
        from src.models.user import User, Subscription, UserWatchlist

        with self._db.get_session() as session:
            now = datetime.now()

            # Get user IDs with active subscriptions
            active_user_ids = (
                session.query(Subscription.user_id)
                .join(User, User.id == Subscription.user_id)
                .filter(
                    User.status == "active",
                    Subscription.status == "active",
                )
                .filter(
                    # Not expired, or no expiry date (unlimited)
                    (Subscription.expire_at.is_(None)) | (Subscription.expire_at > now)
                )
                .distinct()
                .all()
            )

            user_ids = [uid for (uid,) in active_user_ids]
            if not user_ids:
                return []

            # Get unique stock codes from all active users' watchlists
            codes = (
                session.query(UserWatchlist.code)
                .filter(UserWatchlist.user_id.in_(user_ids))
                .distinct()
                .all()
            )

            return sorted(set(c for (c,) in codes))

    def _get_or_create_daily_record(self, code: str, analysis_date: date) -> str:
        """Get or create a StockAnalysisDaily record, return its status."""
        from src.models.stock_analysis import StockAnalysisDaily

        with self._db.get_session() as session:
            record = (
                session.query(StockAnalysisDaily)
                .filter_by(code=code, analysis_date=analysis_date)
                .first()
            )

            if record:
                return record.status

            # Create new pending record
            record = StockAnalysisDaily(
                code=code,
                analysis_date=analysis_date,
                status="pending",
            )
            session.add(record)
            try:
                session.commit()
            except Exception:
                session.rollback()
                # Race condition: another worker created it first
                existing = (
                    session.query(StockAnalysisDaily)
                    .filter_by(code=code, analysis_date=analysis_date)
                    .first()
                )
                return existing.status if existing else "pending"

            return "pending"

    def _analyze_stock(self, code: str, analysis_date: date) -> bool:
        """Analyze a single stock with status tracking.

        1. Update status to 'analyzing'
        2. Run analysis via AnalysisService
        3. Update status to 'completed' with result_id
        4. On error: set 'failed' with error_message
        """
        from src.models.stock_analysis import StockAnalysisDaily

        # Mark as analyzing
        with self._db.get_session() as session:
            record = (
                session.query(StockAnalysisDaily)
                .filter_by(code=code, analysis_date=analysis_date)
                .first()
            )
            if not record or record.status not in ("pending", "failed"):
                return False

            record.status = "analyzing"
            record.started_at = datetime.now()
            session.commit()

        # Run actual analysis
        try:
            from src.services.analysis_service import AnalysisService
            service = AnalysisService()
            result = service.analyze_stock(
                stock_code=code,
                report_type="simple",
                force_refresh=True,
                send_notification=False,
            )

            if not result:
                raise RuntimeError("Analysis returned empty result")

            # Mark completed
            with self._db.get_session() as session:
                record = (
                    session.query(StockAnalysisDaily)
                    .filter_by(code=code, analysis_date=analysis_date)
                    .first()
                )
                if record:
                    record.status = "completed"
                    record.completed_at = datetime.now()
                    # Store the analysis_history record id if available
                    record.result_id = result.get("history_id")
                    record.error_message = None
                    session.commit()

            logger.info(f"Analysis completed for {code}")
            return True

        except Exception as e:
            logger.error(f"Analysis failed for {code}: {e}")
            with self._db.get_session() as session:
                record = (
                    session.query(StockAnalysisDaily)
                    .filter_by(code=code, analysis_date=analysis_date)
                    .first()
                )
                if record:
                    record.status = "failed"
                    record.error_message = str(e)[:500]
                    record.retry_count = (record.retry_count or 0) + 1
                    session.commit()
            return False
