# -*- coding: utf-8 -*-
"""Weekly cron job for strategy backtesting.

Runs every Sunday at 22:00 CST:
1. Run strategy-level backtests on recent data
2. Update strategy ranking
3. Update confidence weights based on backtest results
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class StrategyBacktestSchedulerJob:
    """Weekly strategy backtest job."""

    def __init__(self, limit_stocks: int = 30):
        self._limit_stocks = limit_stocks

    def run(self) -> Dict:
        """Execute weekly strategy backtest cycle.

        Returns:
            Dict with backtest results summary.
        """
        logger.info("Starting weekly strategy backtest job")
        results = {
            "strategies_tested": 0,
            "total_signals": 0,
            "confidence_updated": 0,
            "errors": [],
        }

        try:
            from src.storage import DatabaseManager
            from src.services.strategy_backtest_service import StrategyBacktestService
            from src.core.confidence_engine import ConfidenceEngine

            db = DatabaseManager.get_instance()
            service = StrategyBacktestService(db)

            # Run strategy backtests
            backtest_results = service.run_strategy_backtest(
                limit_stocks=self._limit_stocks
            )
            results["strategies_tested"] = backtest_results.get("strategies_tested", 0)
            results["total_signals"] = sum(
                r.get("total_signals", 0)
                for r in backtest_results.get("results", [])
            )

            # Update confidence scores
            engine = ConfidenceEngine(db=db)
            for r in backtest_results.get("results", []):
                strategy_name = r.get("strategy_name", "")
                if strategy_name:
                    try:
                        engine.update_strategy_confidence(strategy_name)
                        results["confidence_updated"] += 1
                    except Exception as exc:
                        results["errors"].append(f"Confidence update failed for {strategy_name}: {exc}")

        except Exception as exc:
            logger.error("Strategy backtest job failed: %s", exc, exc_info=True)
            results["errors"].append(str(exc))

        logger.info(
            "Strategy backtest job complete: %d strategies, %d signals, %d confidence updates",
            results["strategies_tested"], results["total_signals"], results["confidence_updated"],
        )
        return results
