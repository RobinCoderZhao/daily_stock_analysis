# -*- coding: utf-8 -*-
"""Multi-factor composite scoring engine.

Combines technical, fundamental, money-flow, and market factors
into a single 0-100 score for stock analysis recommendations.

Usage::

    from src.core.multi_factor_scorer import MultiFactorScorer

    scorer = MultiFactorScorer()
    scores = scorer.score(
        trend_result=trend_analysis_result,
        fundamental_data=None,      # from Tushare or None
        money_flow_data=None,       # from Tushare or None
        market_regime="均衡",
    )
    print(scores.total, scores.label)  # e.g. 68.5, "可以关注"

Degradation strategy:
    - Technical (0-40): always available (core indicators)
    - Fundamental (0-30): neutral 15 if no Tushare data
    - Money flow (0-20): neutral 10 if no Tushare data
    - Market (0-10): always available (market regime)
    Without Tushare: max reachable = 40 + 15 + 10 + 5 = 70 ("推荐买入")
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class FactorScores:
    """Breakdown of multi-factor composite score."""
    technical: float        # 0-40
    fundamental: float      # 0-30 (requires Tushare)
    money_flow: float       # 0-20 (requires Tushare 6000)
    market: float           # 0-10
    total: float            # 0-100
    label: str              # "强烈推荐" / "推荐买入" / "可以关注" / "中性观望" / "建议回避"


class MultiFactorScorer:
    """Compute multi-factor composite scores for stock analysis."""

    def score(
        self,
        *,
        trend_result: Any,              # TrendAnalysisResult
        fundamental_data: Optional[Dict] = None,
        money_flow_data: Optional[Dict] = None,
        market_regime: str = "均衡",
    ) -> FactorScores:
        """Compute composite score from all available factors.

        Args:
            trend_result: TrendAnalysisResult from stock_analyzer.
            fundamental_data: Dict from Tushare fina_indicator (optional).
            money_flow_data: Dict from Tushare moneyflow (optional).
            market_regime: Current market regime.

        Returns:
            FactorScores with component breakdown and label.
        """
        technical = self._score_technical(trend_result)
        fundamental = self._score_fundamental(fundamental_data)
        money_flow = self._score_money_flow(money_flow_data)
        market = self._score_market(market_regime)

        total = technical + fundamental + money_flow + market
        label = self._get_label(total)

        return FactorScores(
            technical=round(technical, 2),
            fundamental=round(fundamental, 2),
            money_flow=round(money_flow, 2),
            market=round(market, 2),
            total=round(total, 2),
            label=label,
        )

    def _score_technical(self, trend_result: Any) -> float:
        """Technical factor scoring (0-40).

        Sub-components:
        - Trend strength (0-15): based on trend_status + ma_alignment
        - Volume-price harmony (0-10): volume confirms price direction
        - Indicator resonance (0-10): MACD/RSI/KDJ directional agreement
        - Pattern score (0-5): support/breakout patterns
        """
        if trend_result is None:
            return 20.0  # neutral default

        score = 0.0

        # 1. Trend strength (0-15)
        ts = trend_result.trend_status
        trend_val = ts.value if hasattr(ts, 'value') else str(ts)
        trend_map = {
            "强势多头": 15, "多头排列": 12, "弱势多头": 8,
            "盘整": 5, "弱势空头": 3, "空头排列": 1, "强势空头": 0,
        }
        score += trend_map.get(trend_val, 5)

        # 2. Volume-price harmony (0-10)
        vs = trend_result.volume_status
        vs_val = vs.value if hasattr(vs, 'value') else str(vs)
        vp_map = {
            "放量上涨": 10, "缩量回调": 8, "量能正常": 5,
            "缩量上涨": 4, "放量下跌": 1,
        }
        score += vp_map.get(vs_val, 5)

        # 3. Indicator resonance (0-10)
        resonance = 0
        # MACD bullish
        macd_bar = getattr(trend_result, 'macd_bar', 0) or 0
        if macd_bar > 0:
            resonance += 3

        # RSI assessment
        rsi_12 = getattr(trend_result, 'rsi_12', 50) or 50
        if 30 < rsi_12 < 70:
            resonance += 3
        elif rsi_12 <= 30:
            resonance += 4  # oversold bounce potential

        # KDJ signal
        kdj_signal = getattr(trend_result, 'kdj_signal', '') or ''
        if kdj_signal == "golden_cross":
            resonance += 4
        elif kdj_signal == "neutral":
            resonance += 2
        score += min(resonance, 10)

        # 4. Pattern score (0-5)
        if getattr(trend_result, 'support_ma5', False):
            score += 2
        if getattr(trend_result, 'support_ma10', False):
            score += 1.5
        bias_ma5 = getattr(trend_result, 'bias_ma5', 0) or 0
        if abs(bias_ma5) < 2:
            score += 1.5

        return min(score, 40.0)

    def _score_fundamental(self, data: Optional[Dict]) -> float:
        """Fundamental factor scoring (0-30). Returns 15 if no data.

        Sub-components when data available:
        - ROE quality (0-10): ROE > 15% and stable
        - Valuation (0-10): PE/PB relative to sector median
        - Cash flow health (0-10): operating CF > net income
        """
        if data is None:
            return 15.0  # neutral default when no fundamental data

        score = 0.0

        # ROE quality (0-10)
        roe = data.get("roe", 0) or 0
        if roe >= 20:
            score += 10
        elif roe >= 15:
            score += 8
        elif roe >= 10:
            score += 6
        elif roe >= 5:
            score += 4
        else:
            score += 2

        # Valuation (0-10)
        pe = data.get("pe", 0) or 0
        pe_sector_median = data.get("pe_sector_median", pe) or pe
        if pe > 0 and pe_sector_median > 0:
            pe_ratio = pe / pe_sector_median
            if pe_ratio < 0.7:
                score += 10  # significantly undervalued
            elif pe_ratio < 1.0:
                score += 7  # slightly undervalued
            elif pe_ratio < 1.3:
                score += 5  # fairly valued
            elif pe_ratio < 2.0:
                score += 3  # slightly overvalued
            else:
                score += 1  # significantly overvalued
        else:
            score += 5  # no PE data, neutral

        # Cash flow health (0-10)
        ocf = data.get("operating_cash_flow", 0) or 0
        net_income = data.get("net_income", 0) or 0
        if net_income > 0 and ocf > net_income:
            score += 10  # excellent cash flow quality
        elif net_income > 0 and ocf > 0:
            score += 7  # positive cash flow
        elif ocf > 0:
            score += 4  # positive OCF but negative NI
        else:
            score += 2  # negative cash flow

        return min(score, 30.0)

    def _score_money_flow(self, data: Optional[Dict]) -> float:
        """Money flow factor scoring (0-20). Returns 10 if no data.

        Sub-components when data available:
        - Institutional net inflow (0-10)
        - Chip concentration / turnover (0-10)
        """
        if data is None:
            return 10.0  # neutral default when no money flow data

        score = 0.0

        # Institutional net inflow (0-10)
        net_inflow = data.get("net_inflow_rate", 0) or 0
        if net_inflow > 5:
            score += 10
        elif net_inflow > 2:
            score += 8
        elif net_inflow > 0:
            score += 6
        elif net_inflow > -2:
            score += 4
        else:
            score += 1

        # Chip concentration (0-10)
        concentration = data.get("chip_concentration", 50) or 50
        if concentration > 80:
            score += 10  # highly concentrated (bullish)
        elif concentration > 60:
            score += 7
        elif concentration > 40:
            score += 5
        else:
            score += 3

        return min(score, 20.0)

    def _score_market(self, market_regime: str) -> float:
        """Market environment scoring (0-10)."""
        regime_map = {"进攻": 9, "均衡": 5, "防守": 2}
        return regime_map.get(market_regime, 5)

    @staticmethod
    def _get_label(total: float) -> str:
        """Map total score to recommendation label."""
        if total >= 85:
            return "强烈推荐"
        if total >= 70:
            return "推荐买入"
        if total >= 55:
            return "可以关注"
        if total >= 40:
            return "中性观望"
        return "建议回避"
