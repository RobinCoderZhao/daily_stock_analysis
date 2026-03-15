# -*- coding: utf-8 -*-
"""Portfolio risk management module.

Controls portfolio-level risk through:
1. Total portfolio exposure limits
2. Sector concentration limits
3. Concurrent signal limits
4. Daily new signal limits

Usage::

    from src.core.portfolio_risk_manager import PortfolioRiskManager, PortfolioConfig

    manager = PortfolioRiskManager()
    result = manager.check_signal(
        code="600519", sector="白酒",
        proposed_position_pct=15.0,
        active_signals=[...],
    )
    if result.approved:
        print(f"Approved at {result.adjusted_position_pct}%")
    else:
        print(f"Rejected: {result.rejections}")
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PortfolioConfig:
    """Portfolio risk configuration."""
    max_total_exposure_pct: float = 60.0     # max 60% invested
    max_single_position_pct: float = 20.0    # max 20% per stock
    max_sector_concentration_pct: float = 30.0  # max 30% per sector
    max_concurrent_signals: int = 8          # max 8 active signals
    max_daily_new_signals: int = 3           # max 3 new signals per day
    risk_per_trade_pct: float = 2.0          # max 2% risk per trade
    portfolio_value: float = 100000.0        # default portfolio value


@dataclass
class RiskCheckResult:
    """Result of a portfolio risk check."""
    approved: bool
    original_position_pct: float
    adjusted_position_pct: float
    rejections: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PortfolioRiskManager:
    """Check and adjust positions against portfolio-level risk rules."""

    def __init__(self, config: Optional[PortfolioConfig] = None):
        self.config = config or PortfolioConfig()

    def check_signal(
        self,
        *,
        code: str,
        sector: str,
        proposed_position_pct: float,
        active_signals: List[Dict],  # current active signals with positions
    ) -> RiskCheckResult:
        """Check if a new signal can be accepted.

        Args:
            code: Stock code for the new signal.
            sector: Sector name of the stock.
            proposed_position_pct: Proposed position as % of portfolio.
            active_signals: List of dicts with keys:
                code, sector, position_pct, created_today (bool).

        Returns:
            RiskCheckResult with approval status and adjustments.
        """
        rejections: List[str] = []
        warnings: List[str] = []
        adjusted = proposed_position_pct

        # 1. Check max concurrent signals
        if len(active_signals) >= self.config.max_concurrent_signals:
            rejections.append(
                f"已达最大持仓数 ({self.config.max_concurrent_signals})"
            )
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )

        # 2. Check total exposure
        current_exposure = sum(s.get("position_pct", 0) for s in active_signals)
        remaining = self.config.max_total_exposure_pct - current_exposure
        if remaining <= 0:
            rejections.append(
                f"总仓位已满 ({current_exposure:.1f}%/{self.config.max_total_exposure_pct}%)"
            )
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )
        if adjusted > remaining:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {remaining:.1f}% (总仓位上限)"
            )
            adjusted = remaining

        # 3. Check single position cap
        if adjusted > self.config.max_single_position_pct:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {self.config.max_single_position_pct}% (单股上限)"
            )
            adjusted = self.config.max_single_position_pct

        # 4. Check sector concentration
        sector_exposure = sum(
            s.get("position_pct", 0) for s in active_signals
            if s.get("sector") == sector
        )
        sector_remaining = self.config.max_sector_concentration_pct - sector_exposure
        if sector_remaining <= 0:
            rejections.append(
                f"{sector} 板块仓位已满 ({sector_exposure:.1f}%)"
            )
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )
        if adjusted > sector_remaining:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {sector_remaining:.1f}% (板块上限)"
            )
            adjusted = sector_remaining

        # 5. Daily signal count
        today_signals = [
            s for s in active_signals if s.get("created_today", False)
        ]
        if len(today_signals) >= self.config.max_daily_new_signals:
            rejections.append(
                f"今日新增信号已达上限 ({self.config.max_daily_new_signals}个)"
            )
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )

        # 6. Check duplicate stock
        existing_codes = {s.get("code") for s in active_signals}
        if code in existing_codes:
            warnings.append(f"已持有 {code}，信号将叠加")

        return RiskCheckResult(
            approved=True, original_position_pct=proposed_position_pct,
            adjusted_position_pct=adjusted, rejections=rejections, warnings=warnings,
        )

    @classmethod
    def from_system_config(cls, config_dict: Dict) -> "PortfolioRiskManager":
        """Create from system_config key-value pairs.

        Args:
            config_dict: Dict with keys like 'portfolio.max_total_exposure_pct'.

        Returns:
            PortfolioRiskManager instance.
        """
        pc = PortfolioConfig()
        mappings = {
            "portfolio.max_total_exposure_pct": ("max_total_exposure_pct", float),
            "portfolio.max_single_position_pct": ("max_single_position_pct", float),
            "portfolio.max_sector_concentration_pct": ("max_sector_concentration_pct", float),
            "portfolio.max_concurrent_signals": ("max_concurrent_signals", int),
            "portfolio.max_daily_new_signals": ("max_daily_new_signals", int),
            "portfolio.risk_per_trade_pct": ("risk_per_trade_pct", float),
            "portfolio.value": ("portfolio_value", float),
        }
        for key, (attr, typ) in mappings.items():
            if key in config_dict:
                try:
                    setattr(pc, attr, typ(config_dict[key]))
                except (ValueError, TypeError):
                    pass
        return cls(config=pc)
