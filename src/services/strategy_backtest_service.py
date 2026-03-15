# -*- coding: utf-8 -*-
"""Service layer for strategy-level backtesting.

Orchestrates the strategy backtester against historical stock data,
persists results, and provides ranking/confidence weight updates.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.strategy_backtester import StrategyBacktester, StrategyBacktestResult
from src.core.backtest_engine import EvaluationConfig
from src.repositories.strategy_backtest_repo import StrategyBacktestRepository
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class StrategyBacktestService:
    """Orchestrate strategy-level backtests and persist results."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()
        self.repo = StrategyBacktestRepository(self.db)

    def run_strategy_backtest(
        self,
        strategy_name: Optional[str] = None,
        code: Optional[str] = None,
        limit_stocks: int = 50,
        eval_window_days: int = 10,
    ) -> Dict[str, Any]:
        """Run strategy backtest on historical data.

        If strategy_name is None: run all backtestable strategies.
        If code is None: use stocks from analysis_history.

        Returns:
            Dict with summary of results.
        """
        from src.agent.factory import get_skill_manager

        # Load strategies
        skill_manager = get_skill_manager()
        all_skills = skill_manager.list_skills()
        backtestable = []
        for skill in all_skills:
            if skill.quantitative_rules is None:
                continue
            if skill.quantitative_rules.get("backtestable", True) is False:
                continue
            if strategy_name and skill.name != strategy_name:
                continue
            backtestable.append(skill)

        if not backtestable:
            return {"error": "No backtestable strategies found", "strategies_tested": 0}

        # Get stock codes
        codes = self._get_stock_codes(code, limit_stocks)
        if not codes:
            return {"error": "No stock codes available", "strategies_tested": 0}

        backtester = StrategyBacktester(
            eval_config=EvaluationConfig(eval_window_days=eval_window_days, neutral_band_pct=2.0),
        )

        results_summary = []
        for skill in backtestable:
            rules = skill.quantitative_rules
            buy_conditions = rules.get("buy_conditions", [])
            if not buy_conditions:
                continue

            holding_days = rules.get("holding_days", 10)
            sl_mult = rules.get("stop_loss_atr_multiple", 2.0)
            tp_mult = rules.get("take_profit_atr_multiple", 3.0)

            # Aggregate across all stocks
            all_evaluations = []
            for stock_code in codes:
                try:
                    df = self._fetch_daily_data(stock_code)
                    if df is None or len(df) < 20:
                        continue

                    result = backtester.backtest_strategy(
                        strategy_name=skill.name,
                        buy_conditions=buy_conditions,
                        code=stock_code,
                        df=df,
                        holding_days=holding_days,
                        stop_loss_atr_mult=sl_mult,
                        take_profit_atr_mult=tp_mult,
                    )
                    all_evaluations.extend(result.evaluations)
                except Exception as exc:
                    logger.warning(
                        "Backtest error for %s/%s: %s", skill.name, stock_code, exc,
                    )
                    continue

            # Re-aggregate across all stocks
            final_result = backtester.aggregate_results(skill.name, all_evaluations)

            # Persist signals
            self._save_signals(final_result)

            # Persist summary
            self._save_summary(final_result)

            results_summary.append(final_result.to_dict())
            logger.info(
                "Strategy '%s' backtest complete: %d signals, win_rate=%.2f%%",
                skill.name,
                final_result.total_signals,
                (final_result.win_rate or 0) * 100,
            )

        return {
            "strategies_tested": len(results_summary),
            "results": results_summary,
        }

    def get_strategy_ranking(self) -> List[Dict[str, Any]]:
        """Return all strategies ranked by win_rate_pct descending."""
        return self.repo.get_all_summaries()

    def get_strategy_summary(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Get summary for a specific strategy."""
        return self.repo.get_summary(strategy_name)

    def _get_stock_codes(self, code: Optional[str], limit: int) -> List[str]:
        """Get stock codes to backtest from analysis_history."""
        if code:
            return [code]

        with self.db.get_session() as session:
            from src.storage import AnalysisHistory
            rows = (
                session.query(AnalysisHistory.code)
                .distinct()
                .order_by(AnalysisHistory.code)
                .limit(limit)
                .all()
            )
            return [r[0] for r in rows if r[0]]

    def _fetch_daily_data(self, code: str):
        """Fetch daily OHLCV data for backtesting from local stock_daily table."""
        try:
            import pandas as pd
            from src.storage import StockDaily

            with self.db.get_session() as session:
                rows = (
                    session.query(StockDaily)
                    .filter(StockDaily.code == code)
                    .order_by(StockDaily.date.asc())
                    .all()
                )
                if not rows:
                    logger.debug("No stock_daily data for %s", code)
                    return None

                records = []
                for r in rows:
                    records.append({
                        "date": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume or 0,
                    })
                df = pd.DataFrame(records)
                if df.empty:
                    return None

                # Ensure required columns are valid
                required = {"close", "high", "low"}
                if not required.issubset(set(df.columns)):
                    return None
                if df["close"].isnull().all():
                    return None

                return df
        except Exception as exc:
            logger.warning("Failed to fetch stock_daily for %s: %s", code, exc)
        return None

    def _save_signals(self, result: StrategyBacktestResult) -> None:
        """Save individual signals from backtest result."""
        signals = []
        for ev in result.evaluations:
            sig = ev.signal
            signals.append({
                "strategy_name": sig.strategy_name,
                "code": sig.code,
                "signal_date": sig.signal_date,
                "direction": sig.direction,
                "entry_price": sig.entry_price,
                "stop_loss": sig.stop_loss,
                "take_profit": sig.take_profit,
                "eval_status": ev.eval_status,
                "outcome": ev.outcome,
                "return_pct": ev.return_pct,
                "exit_reason": ev.exit_reason,
                "holding_days": ev.holding_days,
            })
        if signals:
            try:
                self.repo.save_signals_batch(signals)
            except Exception as exc:
                logger.warning("Failed to save signals: %s", exc)

    def _save_summary(self, result: StrategyBacktestResult) -> None:
        """Save strategy backtest summary."""
        try:
            self.repo.upsert_summary({
                "strategy_name": result.strategy_name,
                "total_signals": result.total_signals,
                "win_count": result.win_count,
                "loss_count": result.loss_count,
                "neutral_count": result.neutral_count,
                "win_rate_pct": round(result.win_rate * 100, 2) if result.win_rate is not None else None,
                "avg_return_pct": result.avg_return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "profit_factor": result.profit_factor,
                "sharpe_ratio": result.sharpe_ratio,
                "avg_holding_days": result.avg_holding_days,
                "stop_loss_trigger_rate": result.stop_loss_trigger_rate,
                "take_profit_trigger_rate": result.take_profit_trigger_rate,
            })
        except Exception as exc:
            logger.warning("Failed to save summary for %s: %s", result.strategy_name, exc)
