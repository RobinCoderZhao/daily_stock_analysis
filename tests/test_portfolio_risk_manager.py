# -*- coding: utf-8 -*-
"""Tests for PortfolioRiskManager."""

import pytest
from src.core.portfolio_risk_manager import PortfolioRiskManager, PortfolioConfig, RiskCheckResult


class TestPortfolioRiskManager:
    """Test portfolio risk checks."""

    def setup_method(self):
        self.manager = PortfolioRiskManager()

    def test_approve_empty_portfolio(self):
        """New signal on empty portfolio should be approved."""
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=15.0,
            active_signals=[],
        )
        assert result.approved is True
        assert result.adjusted_position_pct == 15.0
        assert len(result.rejections) == 0

    def test_reject_max_concurrent_signals(self):
        """Should reject when max concurrent signals reached."""
        signals = [
            {"code": f"60000{i}", "sector": f"s{i}", "position_pct": 5.0}
            for i in range(8)  # max = 8
        ]
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=10.0,
            active_signals=signals,
        )
        assert result.approved is False
        assert "最大持仓数" in result.rejections[0]

    def test_adjust_total_exposure(self):
        """Should adjust position when total exposure would exceed limit."""
        signals = [
            {"code": "600001", "sector": "银行", "position_pct": 50.0}
        ]
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=15.0,
            active_signals=signals,
        )
        assert result.approved is True
        assert result.adjusted_position_pct == 10.0  # 60 - 50 = 10
        assert len(result.warnings) > 0

    def test_reject_total_exposure_full(self):
        """Should reject when total exposure is already at limit."""
        signals = [
            {"code": "600001", "sector": "银行", "position_pct": 60.0}
        ]
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=10.0,
            active_signals=signals,
        )
        assert result.approved is False
        assert "总仓位已满" in result.rejections[0]

    def test_cap_single_position(self):
        """Should cap single position at max_single_position_pct."""
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=25.0,
            active_signals=[],
        )
        assert result.approved is True
        assert result.adjusted_position_pct == 20.0  # max single = 20%

    def test_sector_concentration_rejection(self):
        """Should reject when sector concentration is at limit."""
        signals = [
            {"code": "600519", "sector": "白酒", "position_pct": 15.0},
            {"code": "000858", "sector": "白酒", "position_pct": 15.0},
        ]
        result = self.manager.check_signal(
            code="002304", sector="白酒",
            proposed_position_pct=5.0,
            active_signals=signals,
        )
        assert result.approved is False
        assert "板块仓位已满" in result.rejections[0]

    def test_sector_concentration_adjustment(self):
        """Should adjust position when sector is near limit."""
        signals = [
            {"code": "600519", "sector": "白酒", "position_pct": 20.0},
        ]
        result = self.manager.check_signal(
            code="000858", sector="白酒",
            proposed_position_pct=15.0,
            active_signals=signals,
        )
        assert result.approved is True
        assert result.adjusted_position_pct == 10.0  # 30 - 20 = 10

    def test_daily_signal_limit(self):
        """Should reject when daily new signal limit is reached."""
        signals = [
            {"code": f"60000{i}", "sector": "s", "position_pct": 5.0, "created_today": True}
            for i in range(3)  # max = 3
        ]
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=10.0,
            active_signals=signals,
        )
        assert result.approved is False
        assert "今日新增信号已达上限" in result.rejections[0]

    def test_duplicate_stock_warning(self):
        """Should warn when stock already in portfolio."""
        signals = [
            {"code": "600519", "sector": "白酒", "position_pct": 10.0},
        ]
        result = self.manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=5.0,
            active_signals=signals,
        )
        assert result.approved is True
        assert any("已持有" in w for w in result.warnings)

    def test_custom_config(self):
        """Custom config should be respected."""
        config = PortfolioConfig(
            max_total_exposure_pct=40.0,
            max_single_position_pct=10.0,
            max_concurrent_signals=3,
        )
        manager = PortfolioRiskManager(config=config)
        result = manager.check_signal(
            code="600519", sector="白酒",
            proposed_position_pct=15.0,
            active_signals=[],
        )
        assert result.adjusted_position_pct == 10.0  # single cap = 10%

    def test_from_system_config(self):
        """Should create manager from system config dict."""
        config_dict = {
            "portfolio.max_total_exposure_pct": "50",
            "portfolio.max_concurrent_signals": "5",
            "portfolio.value": "200000",
        }
        manager = PortfolioRiskManager.from_system_config(config_dict)
        assert manager.config.max_total_exposure_pct == 50.0
        assert manager.config.max_concurrent_signals == 5
        assert manager.config.portfolio_value == 200000.0
