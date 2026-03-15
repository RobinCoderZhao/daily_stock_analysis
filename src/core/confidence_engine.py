# -*- coding: utf-8 -*-
"""Signal confidence scoring engine.

Replaces static confidence_weight in strategy YAMLs with data-driven
dynamic confidence scores based on backtest results and market conditions.

Usage::

    from src.core.confidence_engine import ConfidenceEngine

    engine = ConfidenceEngine(db)
    factors = engine.compute(
        strategy_name="bull_trend",
        code="600519",
        concurrent_strategies=["ma_golden_cross"],
        market_regime="均衡",
        recent_signal_count=1,
    )
    print(factors.final_score)  # 0-100
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceFactors:
    """Breakdown of confidence score components."""
    base_score: float         # from backtest win_rate + profit_factor + sharpe (0-100)
    market_modifier: float    # market regime adjustment (0.5-1.5)
    resonance_bonus: float    # multi-strategy confirmation bonus (1.0-1.5)
    decay_factor: float       # signal fatigue reduction (0-1.0)
    final_score: float        # combined (0-100)


class ConfidenceEngine:
    """Compute dynamic confidence scores for trading signals.

    The confidence score combines:
    1. Base score from backtest metrics (win_rate, profit_factor, sharpe)
    2. Market regime adjustment (offensive/balanced/defensive)
    3. Multi-strategy resonance bonus (when multiple strategies agree)
    4. Signal decay (reduces confidence for repeatedly triggered signals)
    """

    # Market regime multipliers
    _REGIME_MODIFIERS: Dict[str, float] = {
        "进攻": 1.2,
        "均衡": 1.0,
        "防守": 0.6,
    }

    # Default backtest metrics when no data available
    _DEFAULT_WIN_RATE = 50.0
    _DEFAULT_PROFIT_FACTOR = 1.0
    _DEFAULT_SHARPE = 0.0

    def __init__(self, db=None):
        """Initialize with optional database for backtest data lookup.

        Args:
            db: DatabaseManager instance. If None, uses default base scores.
        """
        self._db = db
        self._cache: Dict[str, Dict] = {}  # strategy_name -> backtest metrics

    def compute(
        self,
        strategy_name: str,
        code: str,
        concurrent_strategies: Optional[List[str]] = None,
        market_regime: str = "均衡",
        recent_signal_count: int = 0,
    ) -> ConfidenceFactors:
        """Compute confidence score for a signal.

        Args:
            strategy_name: Name of the strategy that generated the signal.
            code: Stock code for context.
            concurrent_strategies: Other strategies that triggered on the same stock.
            market_regime: Current market regime ("进攻" / "均衡" / "防守").
            recent_signal_count: Same strategy signals in last 5 days (for decay).

        Returns:
            ConfidenceFactors with component breakdown and final score.
        """
        if concurrent_strategies is None:
            concurrent_strategies = []

        # 1. Base score from backtest metrics
        metrics = self._get_backtest_metrics(strategy_name)
        base_score = self._compute_base_score(metrics)

        # 2. Market regime modifier
        market_modifier = self._REGIME_MODIFIERS.get(market_regime, 1.0)

        # 3. Resonance bonus: more strategies agreeing = more confidence
        resonance_count = len(concurrent_strategies)
        resonance_bonus = min(1.0 + 0.1 * resonance_count, 1.5)

        # 4. Decay factor: repeated signals reduce confidence
        decay_factor = 1.0 / (1.0 + 0.2 * recent_signal_count)

        # Combine
        raw_score = base_score * market_modifier * resonance_bonus * decay_factor
        final_score = max(0.0, min(100.0, raw_score))

        return ConfidenceFactors(
            base_score=round(base_score, 2),
            market_modifier=round(market_modifier, 2),
            resonance_bonus=round(resonance_bonus, 2),
            decay_factor=round(decay_factor, 4),
            final_score=round(final_score, 2),
        )

    def _compute_base_score(self, metrics: Dict) -> float:
        """Compute base score from backtest metrics.

        Formula:
            base = 40 * norm(win_rate, 0.4, 0.7)
                 + 35 * norm(profit_factor, 0.8, 2.5)
                 + 25 * norm(sharpe, 0, 2)

        All values normalized to 0-1 range before weighting.
        """
        win_rate = metrics.get("win_rate_pct", self._DEFAULT_WIN_RATE) or self._DEFAULT_WIN_RATE
        profit_factor = metrics.get("profit_factor", self._DEFAULT_PROFIT_FACTOR) or self._DEFAULT_PROFIT_FACTOR
        sharpe = metrics.get("sharpe_ratio", self._DEFAULT_SHARPE) or self._DEFAULT_SHARPE

        # Convert win_rate from percentage (0-100) to ratio (0-1)
        win_rate_ratio = win_rate / 100.0

        score = (
            40.0 * self._normalize(win_rate_ratio, 0.4, 0.7)
            + 35.0 * self._normalize(profit_factor, 0.8, 2.5)
            + 25.0 * self._normalize(sharpe, 0.0, 2.0)
        )
        return score

    def _get_backtest_metrics(self, strategy_name: str) -> Dict:
        """Fetch backtest metrics for a strategy from DB cache.

        Returns dict with keys: win_rate_pct, profit_factor, sharpe_ratio.
        Uses cached values to avoid repeated DB queries.
        """
        if strategy_name in self._cache:
            return self._cache[strategy_name]

        metrics = {
            "win_rate_pct": self._DEFAULT_WIN_RATE,
            "profit_factor": self._DEFAULT_PROFIT_FACTOR,
            "sharpe_ratio": self._DEFAULT_SHARPE,
        }

        if self._db is not None:
            try:
                from src.storage import StrategyBacktestSummary

                with self._db.get_session() as session:
                    summary = (
                        session.query(StrategyBacktestSummary)
                        .filter(StrategyBacktestSummary.strategy_name == strategy_name)
                        .first()
                    )
                    if summary and summary.total_signals > 0:
                        metrics["win_rate_pct"] = summary.win_rate_pct or self._DEFAULT_WIN_RATE
                        metrics["profit_factor"] = summary.profit_factor or self._DEFAULT_PROFIT_FACTOR
                        metrics["sharpe_ratio"] = summary.sharpe_ratio or self._DEFAULT_SHARPE
            except Exception as exc:
                logger.warning("Failed to fetch backtest metrics for %s: %s", strategy_name, exc)

        self._cache[strategy_name] = metrics
        return metrics

    def update_strategy_confidence(self, strategy_name: str) -> Optional[float]:
        """Compute and persist confidence score for a strategy.

        Used after backtest completes to update StrategyBacktestSummary.computed_confidence.

        Returns:
            The computed confidence score, or None on failure.
        """
        factors = self.compute(strategy_name=strategy_name, code="")
        if self._db is None:
            return factors.final_score

        try:
            from src.storage import StrategyBacktestSummary

            with self._db.get_session() as session:
                summary = (
                    session.query(StrategyBacktestSummary)
                    .filter(StrategyBacktestSummary.strategy_name == strategy_name)
                    .first()
                )
                if summary:
                    summary.computed_confidence = factors.final_score
                    session.commit()
                    logger.info("Updated confidence for %s: %.2f", strategy_name, factors.final_score)
                    return factors.final_score
        except Exception as exc:
            logger.warning("Failed to update confidence for %s: %s", strategy_name, exc)
        return None

    @staticmethod
    def _normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range."""
        if max_val <= min_val:
            return 0.5
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
