# -*- coding: utf-8 -*-
"""Tests for ConfidenceEngine."""

import pytest
from unittest.mock import MagicMock, patch
from src.core.confidence_engine import ConfidenceEngine, ConfidenceFactors


class TestConfidenceEngineNoDB:
    """Test confidence engine without database (default metrics)."""

    def setup_method(self):
        self.engine = ConfidenceEngine(db=None)

    def test_default_confidence_balanced_market(self):
        """Default metrics in balanced market should produce moderate score."""
        factors = self.engine.compute(
            strategy_name="test_strategy",
            code="600519",
            market_regime="均衡",
        )
        assert isinstance(factors, ConfidenceFactors)
        assert 0 <= factors.final_score <= 100
        assert factors.market_modifier == 1.0
        assert factors.resonance_bonus == 1.0
        assert factors.decay_factor == 1.0

    def test_offensive_market_increases_score(self):
        """Offensive market regime should increase score."""
        balanced = self.engine.compute(strategy_name="s", code="c", market_regime="均衡")
        offensive = self.engine.compute(strategy_name="s", code="c", market_regime="进攻")
        assert offensive.final_score > balanced.final_score
        assert offensive.market_modifier == 1.2

    def test_defensive_market_decreases_score(self):
        """Defensive market regime should decrease score."""
        balanced = self.engine.compute(strategy_name="s", code="c", market_regime="均衡")
        defensive = self.engine.compute(strategy_name="s", code="c", market_regime="防守")
        assert defensive.final_score < balanced.final_score
        assert defensive.market_modifier == 0.6

    def test_resonance_bonus(self):
        """Multiple concurrent strategies should increase score."""
        single = self.engine.compute(
            strategy_name="s", code="c",
            concurrent_strategies=[],
        )
        multi = self.engine.compute(
            strategy_name="s", code="c",
            concurrent_strategies=["a", "b", "c"],
        )
        assert multi.resonance_bonus == 1.3
        assert multi.final_score > single.final_score

    def test_resonance_bonus_caps_at_1_5(self):
        """Resonance bonus should not exceed 1.5."""
        factors = self.engine.compute(
            strategy_name="s", code="c",
            concurrent_strategies=["a", "b", "c", "d", "e", "f", "g"],
        )
        assert factors.resonance_bonus == 1.5

    def test_signal_decay(self):
        """Repeated signals should reduce confidence."""
        fresh = self.engine.compute(
            strategy_name="s", code="c",
            recent_signal_count=0,
        )
        repeated = self.engine.compute(
            strategy_name="s", code="c",
            recent_signal_count=5,
        )
        assert repeated.final_score < fresh.final_score
        assert repeated.decay_factor < 1.0

    def test_score_bounds(self):
        """Score should always be between 0 and 100."""
        # Extreme positive case
        factors = self.engine.compute(
            strategy_name="s", code="c",
            concurrent_strategies=["a", "b", "c", "d", "e"],
            market_regime="进攻",
            recent_signal_count=0,
        )
        assert 0 <= factors.final_score <= 100

        # Extreme negative case
        factors = self.engine.compute(
            strategy_name="s", code="c",
            concurrent_strategies=[],
            market_regime="防守",
            recent_signal_count=10,
        )
        assert 0 <= factors.final_score <= 100


class TestNormalize:
    """Test the _normalize static method."""

    def test_below_min(self):
        assert ConfidenceEngine._normalize(0.2, 0.4, 0.7) == 0.0

    def test_above_max(self):
        assert ConfidenceEngine._normalize(1.0, 0.4, 0.7) == 1.0

    def test_midpoint(self):
        result = ConfidenceEngine._normalize(0.55, 0.4, 0.7)
        assert abs(result - 0.5) < 0.01

    def test_equal_min_max(self):
        assert ConfidenceEngine._normalize(5.0, 5.0, 5.0) == 0.5


class TestBaseScore:
    """Test base score computation logic."""

    def test_high_win_rate_high_base(self):
        """High win rate + high profit factor should give high base score."""
        engine = ConfidenceEngine(db=None)
        engine._cache["good_strategy"] = {
            "win_rate_pct": 70.0,     # 70% win rate
            "profit_factor": 2.5,
            "sharpe_ratio": 2.0,
        }
        factors = engine.compute(strategy_name="good_strategy", code="c")
        assert factors.base_score > 80

    def test_low_win_rate_low_base(self):
        """Low win rate + low profit factor should give low base score."""
        engine = ConfidenceEngine(db=None)
        engine._cache["bad_strategy"] = {
            "win_rate_pct": 30.0,
            "profit_factor": 0.5,
            "sharpe_ratio": -0.5,
        }
        factors = engine.compute(strategy_name="bad_strategy", code="c")
        assert factors.base_score < 20

    def test_zero_win_rate(self):
        """Zero win rate should not crash."""
        engine = ConfidenceEngine(db=None)
        engine._cache["zero"] = {
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
        }
        factors = engine.compute(strategy_name="zero", code="c")
        assert factors.base_score >= 0

    def test_perfect_win_rate(self):
        """100% win rate should give max base score."""
        engine = ConfidenceEngine(db=None)
        engine._cache["perfect"] = {
            "win_rate_pct": 100.0,
            "profit_factor": 10.0,
            "sharpe_ratio": 5.0,
        }
        factors = engine.compute(strategy_name="perfect", code="c")
        assert factors.base_score == 100.0
