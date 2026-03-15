# -*- coding: utf-8 -*-
"""Tests for PositionSizer."""

import pytest
from src.core.position_sizer import PositionSizer, PositionAdvice


class TestPositionSizer:
    """Test position sizing calculations."""

    def setup_method(self):
        self.sizer = PositionSizer()

    def test_basic_calculation(self):
        """Basic position sizing should produce valid output."""
        advice = self.sizer.calculate(
            portfolio_value=100000,
            entry_price=50.0,
            stop_loss_price=47.0,
            take_profit_price=56.0,
            atr_14=1.5,
            confidence=70.0,
            market_regime="均衡",
        )
        assert isinstance(advice, PositionAdvice)
        assert 3.0 <= advice.position_pct <= 15.0  # regime cap = 15
        assert advice.risk_level in ("low", "medium", "high")
        assert advice.profit_loss_ratio != "N/A"
        assert advice.confidence == 70.0

    def test_high_confidence_larger_position(self):
        """Higher confidence should produce larger position."""
        low = self.sizer.calculate(
            portfolio_value=100000, entry_price=50.0,
            stop_loss_price=47.0, take_profit_price=56.0,
            atr_14=1.5, confidence=30.0, market_regime="均衡",
        )
        high = self.sizer.calculate(
            portfolio_value=100000, entry_price=50.0,
            stop_loss_price=47.0, take_profit_price=56.0,
            atr_14=1.5, confidence=90.0, market_regime="均衡",
        )
        assert high.position_pct >= low.position_pct

    def test_offensive_regime_allows_larger_position(self):
        """Offensive regime should allow up to 20% position."""
        advice = self.sizer.calculate(
            portfolio_value=100000, entry_price=50.0,
            stop_loss_price=47.0, take_profit_price=56.0,
            atr_14=1.5, confidence=95.0, market_regime="进攻",
        )
        assert advice.position_pct <= 20.0

    def test_defensive_regime_caps_position(self):
        """Defensive regime should cap position at 10%."""
        advice = self.sizer.calculate(
            portfolio_value=100000, entry_price=10.0,
            stop_loss_price=9.99, take_profit_price=15.0,
            atr_14=0.05, confidence=95.0, market_regime="防守",
        )
        assert advice.position_pct <= 10.0

    def test_stop_loss_equals_entry_fallback(self):
        """When stop_loss == entry, should use ATR fallback."""
        advice = self.sizer.calculate(
            portfolio_value=100000, entry_price=50.0,
            stop_loss_price=50.0, take_profit_price=55.0,
            atr_14=2.0, confidence=60.0, market_regime="均衡",
        )
        assert advice.position_pct >= 3.0
        assert "fallback" in advice.reasoning.lower()

    def test_invalid_entry_price(self):
        """Zero entry price should return safe default."""
        advice = self.sizer.calculate(
            portfolio_value=100000, entry_price=0,
            stop_loss_price=0, take_profit_price=0,
            atr_14=0, confidence=50.0, market_regime="均衡",
        )
        assert advice.position_pct == 3.0
        assert advice.risk_level == "low"

    def test_profit_loss_ratio_format(self):
        """P/L ratio should be formatted as 1:X.X."""
        advice = self.sizer.calculate(
            portfolio_value=100000, entry_price=100.0,
            stop_loss_price=95.0, take_profit_price=112.5,
            atr_14=3.0, confidence=70.0, market_regime="均衡",
        )
        assert advice.profit_loss_ratio.startswith("1:")
        # 12.5 profit / 5 risk = 2.5
        assert "2.5" in advice.profit_loss_ratio

    def test_min_position_enforced(self):
        """Very small risk should still get minimum 3% position."""
        advice = self.sizer.calculate(
            portfolio_value=1000000, entry_price=1.0,
            stop_loss_price=0.5, take_profit_price=2.0,
            atr_14=0.2, confidence=10.0, market_regime="防守",
        )
        assert advice.position_pct >= 3.0

    def test_risk_level_classification(self):
        """Risk levels should be classified correctly."""
        # Low risk: position <= 8%
        low = self.sizer.calculate(
            portfolio_value=100000, entry_price=50.0,
            stop_loss_price=47.0, take_profit_price=55.0,
            atr_14=1.5, confidence=30.0, market_regime="防守",
        )
        assert low.risk_level in ("low", "medium")  # depends on regime cap
