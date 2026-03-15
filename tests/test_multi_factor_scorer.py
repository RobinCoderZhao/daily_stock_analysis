# -*- coding: utf-8 -*-
"""Tests for MultiFactorScorer."""

import pytest
from dataclasses import dataclass, field
from typing import List
from src.core.multi_factor_scorer import MultiFactorScorer, FactorScores


@dataclass
class MockTrendResult:
    """Mock TrendAnalysisResult for testing."""
    code: str = "600519"
    trend_status: str = "多头排列"
    volume_status: str = "放量上涨"
    macd_bar: float = 0.5
    rsi_12: float = 55.0
    kdj_signal: str = "golden_cross"
    support_ma5: bool = True
    support_ma10: bool = True
    bias_ma5: float = 1.0


@dataclass
class MockBearishTrend:
    """Mock bearish trend for testing."""
    code: str = "600519"
    trend_status: str = "强势空头"
    volume_status: str = "放量下跌"
    macd_bar: float = -0.8
    rsi_12: float = 25.0
    kdj_signal: str = "dead_cross"
    support_ma5: bool = False
    support_ma10: bool = False
    bias_ma5: float = -5.0


class TestMultiFactorScorer:
    """Test multi-factor composite scoring."""

    def setup_method(self):
        self.scorer = MultiFactorScorer()

    def test_full_score_bullish(self):
        """Bullish trend with all factors should score high."""
        scores = self.scorer.score(
            trend_result=MockTrendResult(),
            fundamental_data={"roe": 25, "pe": 15, "pe_sector_median": 25,
                              "operating_cash_flow": 100, "net_income": 80},
            money_flow_data={"net_inflow_rate": 6, "chip_concentration": 85},
            market_regime="进攻",
        )
        assert isinstance(scores, FactorScores)
        assert scores.technical > 25
        assert scores.fundamental > 20
        assert scores.money_flow > 15
        assert scores.market == 9
        assert scores.total > 70

    def test_no_fundamental_data_defaults(self):
        """No fundamental data should give neutral 15."""
        scores = self.scorer.score(
            trend_result=MockTrendResult(),
            fundamental_data=None,
            market_regime="均衡",
        )
        assert scores.fundamental == 15.0

    def test_no_money_flow_data_defaults(self):
        """No money flow data should give neutral 10."""
        scores = self.scorer.score(
            trend_result=MockTrendResult(),
            money_flow_data=None,
            market_regime="均衡",
        )
        assert scores.money_flow == 10.0

    def test_degraded_mode_max_score(self):
        """Without Tushare data, max possible ≈ 70 (推荐买入)."""
        scores = self.scorer.score(
            trend_result=MockTrendResult(),
            fundamental_data=None,
            money_flow_data=None,
            market_regime="进攻",
        )
        # technical(max 40) + fundamental(15) + money_flow(10) + market(9) = 74 max
        assert scores.total <= 74
        assert scores.label in ("推荐买入", "可以关注")

    def test_bearish_trend_low_technical(self):
        """Bearish trend should score low on technical."""
        scores = self.scorer.score(
            trend_result=MockBearishTrend(),
            market_regime="防守",
        )
        assert scores.technical < 15
        assert scores.market == 2

    def test_label_mapping(self):
        """Labels should match score ranges."""
        assert MultiFactorScorer._get_label(90) == "强烈推荐"
        assert MultiFactorScorer._get_label(75) == "推荐买入"
        assert MultiFactorScorer._get_label(60) == "可以关注"
        assert MultiFactorScorer._get_label(45) == "中性观望"
        assert MultiFactorScorer._get_label(30) == "建议回避"

    def test_score_ranges_valid(self):
        """All sub-scores should be within their valid ranges."""
        scores = self.scorer.score(
            trend_result=MockTrendResult(),
            fundamental_data={"roe": 15, "pe": 20, "pe_sector_median": 20,
                              "operating_cash_flow": 50, "net_income": 50},
            money_flow_data={"net_inflow_rate": 3, "chip_concentration": 60},
            market_regime="均衡",
        )
        assert 0 <= scores.technical <= 40
        assert 0 <= scores.fundamental <= 30
        assert 0 <= scores.money_flow <= 20
        assert 0 <= scores.market <= 10
        assert 0 <= scores.total <= 100

    def test_none_trend_result(self):
        """None trend_result should give neutral technical score."""
        scores = self.scorer.score(
            trend_result=None,
            market_regime="均衡",
        )
        assert scores.technical == 20.0

    def test_market_regimes(self):
        """Different market regimes should give different scores."""
        offensive = self.scorer.score(trend_result=MockTrendResult(), market_regime="进攻")
        balanced = self.scorer.score(trend_result=MockTrendResult(), market_regime="均衡")
        defensive = self.scorer.score(trend_result=MockTrendResult(), market_regime="防守")
        assert offensive.market > balanced.market > defensive.market
