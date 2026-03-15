# -*- coding: utf-8 -*-
"""Position sizing based on ATR and confidence.

Calculates optimal position size using Fixed Fractional Risk method,
adjusted by signal confidence and market regime.

Usage::

    from src.core.position_sizer import PositionSizer

    sizer = PositionSizer()
    advice = sizer.calculate(
        portfolio_value=100000,
        entry_price=50.0,
        stop_loss_price=47.0,
        take_profit_price=56.0,
        atr_14=1.5,
        confidence=72.0,
        market_regime="均衡",
    )
    print(advice.position_pct)   # e.g. 12.5
    print(advice.risk_level)     # e.g. "medium"
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PositionAdvice:
    """Position sizing recommendation."""
    position_pct: float         # suggested % of portfolio (e.g. 15.0)
    risk_amount: float          # max risk in currency
    profit_loss_ratio: str      # e.g. "1:2.5"
    confidence: float           # from ConfidenceEngine (0-100)
    risk_level: str             # "low" / "medium" / "high"
    reasoning: str              # human-readable explanation


class PositionSizer:
    """Calculate position size based on risk management rules.

    Method: Fixed Fractional Risk
    - Risk a fixed percentage of portfolio per trade
    - Scale by confidence score
    - Cap by market regime
    """

    DEFAULT_RISK_PER_TRADE = 0.02   # 2% of portfolio per trade
    MAX_SINGLE_POSITION = 0.20      # max 20% in one stock
    MIN_POSITION = 0.03             # min 3% to be meaningful

    # Max position cap by market regime
    _REGIME_CAPS = {
        "进攻": 0.20,
        "均衡": 0.15,
        "防守": 0.10,
    }

    def calculate(
        self,
        *,
        portfolio_value: float,     # total portfolio value
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        atr_14: float,
        confidence: float,          # 0-100 from ConfidenceEngine
        market_regime: str = "均衡",
    ) -> PositionAdvice:
        """Calculate position size.

        Args:
            portfolio_value: Total portfolio value in currency.
            entry_price: Planned entry price.
            stop_loss_price: Stop loss price.
            take_profit_price: Take profit target price.
            atr_14: 14-day Average True Range.
            confidence: Confidence score 0-100.
            market_regime: Market regime ("进攻" / "均衡" / "防守").

        Returns:
            PositionAdvice with sizing recommendation.
        """
        reasons = []

        # Validate inputs
        if entry_price <= 0 or portfolio_value <= 0:
            return self._default_advice(confidence, "Invalid entry price or portfolio value")

        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            # Fall back to 2 × ATR for stop loss distance
            risk_per_share = max(atr_14 * 2.0, entry_price * 0.03)
            reasons.append(f"Stop loss = entry, using 2×ATR fallback ({risk_per_share:.2f})")

        # Confidence scaling: 0-100 maps to 0.3-1.0 multiplier
        confidence_scale = 0.3 + 0.7 * (max(0.0, min(100.0, confidence)) / 100.0)

        # Risk amount = risk_per_trade × portfolio × confidence_scale
        risk_amount = self.DEFAULT_RISK_PER_TRADE * portfolio_value * confidence_scale

        # Number of shares
        num_shares = risk_amount / risk_per_share
        position_value = num_shares * entry_price
        position_pct = (position_value / portfolio_value) * 100.0

        # Apply regime cap
        regime_cap_pct = self._REGIME_CAPS.get(market_regime, 0.15) * 100.0
        if position_pct > regime_cap_pct:
            reasons.append(
                f"Position {position_pct:.1f}% capped to {regime_cap_pct:.1f}% ({market_regime} regime)"
            )
            position_pct = regime_cap_pct

        # Apply absolute max cap
        max_pct = self.MAX_SINGLE_POSITION * 100.0
        if position_pct > max_pct:
            position_pct = max_pct
            reasons.append(f"Position capped to max {max_pct:.0f}%")

        # Apply min threshold
        if position_pct < self.MIN_POSITION * 100.0:
            reasons.append(f"Position {position_pct:.1f}% below minimum {self.MIN_POSITION * 100:.0f}%, set to min")
            position_pct = self.MIN_POSITION * 100.0

        # Profit/loss ratio
        profit_per_share = abs(take_profit_price - entry_price)
        if risk_per_share > 0 and profit_per_share > 0:
            pl_ratio = profit_per_share / risk_per_share
            pl_ratio_str = f"1:{pl_ratio:.1f}"
        else:
            pl_ratio_str = "N/A"

        # Risk level classification
        if position_pct > 15:
            risk_level = "high"
        elif position_pct > 8:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Final risk amount based on actual position
        actual_position_value = portfolio_value * position_pct / 100.0
        actual_risk = actual_position_value * (risk_per_share / entry_price)

        if not reasons:
            reasons.append(
                f"Based on {self.DEFAULT_RISK_PER_TRADE * 100:.0f}% risk, "
                f"confidence {confidence:.0f}, {market_regime} regime"
            )

        return PositionAdvice(
            position_pct=round(position_pct, 2),
            risk_amount=round(actual_risk, 2),
            profit_loss_ratio=pl_ratio_str,
            confidence=round(confidence, 2),
            risk_level=risk_level,
            reasoning="; ".join(reasons),
        )

    def _default_advice(self, confidence: float, reason: str) -> PositionAdvice:
        """Return safe default position advice."""
        return PositionAdvice(
            position_pct=self.MIN_POSITION * 100.0,
            risk_amount=0.0,
            profit_loss_ratio="N/A",
            confidence=confidence,
            risk_level="low",
            reasoning=reason,
        )
