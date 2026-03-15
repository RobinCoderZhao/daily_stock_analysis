# Phase 2 开发文档：置信度引擎 + 仓位管理 + 多因子评分

> 本阶段目标：将 Phase 1 的回测数据转化为可操作的交易建议（置信度 + 仓位 + 综合评分）。
> 前置依赖：Phase 1 全部完成（策略回测产出数据 + 信号跟踪表可用）
>
> **Phase 1 变更备注**：
> - `DatabaseManager.get_session()` 已改为懒初始化（无需担心启动时序）
> - `_fetch_daily_data` 优先使用本地 `stock_daily` 表，有 Tushare token 时走 API
> - 前端构建已修复 `vite.config.ts` 使用 `loadEnv()` 读取 `.env.production`，直接 `npm run build` 即可
> 预计工期：3-4 周

---

## 1. 信号置信度引擎

### 1.1 核心逻辑

#### [NEW] `src/core/confidence_engine.py`

```python
"""Signal confidence scoring engine.

Replaces static confidence_weight in strategy YAMLs with data-driven
dynamic confidence scores based on backtest results and market conditions.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ConfidenceFactors:
    """Breakdown of confidence score components."""
    base_score: float         # from backtest win_rate + profit_factor
    market_modifier: float    # market regime adjustment (0.5-1.5)
    resonance_bonus: float    # multi-strategy confirmation bonus
    decay_factor: float       # signal fatigue reduction
    final_score: float        # combined (0-100)


class ConfidenceEngine:
    """Compute dynamic confidence scores for trading signals."""

    def compute(
        self,
        strategy_name: str,
        code: str,
        concurrent_strategies: List[str],
        market_regime: str,  # "进攻" / "均衡" / "防守"
        recent_signal_count: int,  # same strategy signals in last 5 days
    ) -> ConfidenceFactors:
        """Compute confidence score.

        Formula:
        final = base_score × market_modifier × resonance_bonus × decay_factor

        Components:
        - base_score: f(backtest_win_rate, profit_factor, sharpe)
          = 40 * norm(win_rate, 0.4, 0.7) + 35 * norm(profit_factor, 0.8, 2.5) + 25 * norm(sharpe, 0, 2)
        - market_modifier: {"进攻": 1.2, "均衡": 1.0, "防守": 0.6}
        - resonance_bonus: 1.0 + 0.1 * (len(concurrent_strategies) - 1), max 1.5
        - decay_factor: 1.0 / (1.0 + 0.2 * recent_signal_count)
        """
        ...

    @staticmethod
    def _normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range."""
        if max_val <= min_val:
            return 0.5
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
```

### 1.2 数据来源映射

| 因子 | 数据来源 | 获取方式 |
| --- | --- | --- |
| `backtest_win_rate` | `StrategyBacktestSummary.win_rate_pct` | Phase 1 回测产出 |
| `profit_factor` | `StrategyBacktestSummary.profit_factor` | Phase 1 回测产出 |
| `sharpe_ratio` | `StrategyBacktestSummary.sharpe_ratio` | Phase 1 回测产出 |
| `market_regime` | `MarketStrategyBlueprint.action_framework` | 现有 `market_strategy.py` |
| `concurrent_strategies` | 当前分析中同时触发的策略列表 | `RuleEvaluator` 实时评估 |
| `recent_signal_count` | `Signal` 表近 5 天同策略信号数 | DB 查询 |

### 1.3 集成点

#### [MODIFY] `src/services/analysis_service.py`

在分析报告生成后，调用 `ConfidenceEngine.compute()` 计算置信度，写入报告。

#### [MODIFY] `src/services/signal_service.py`

`create_signal_from_report()` 时将置信度写入 `Signal.confidence`。

---

## 2. 仓位管理模型

#### [NEW] `src/core/position_sizer.py`

```python
"""Position sizing based on ATR and confidence."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionAdvice:
    """Position sizing recommendation."""
    position_pct: float         # suggested % of portfolio (e.g. 15.0)
    risk_amount: float          # max risk in currency
    profit_loss_ratio: str      # e.g. "1:2.5"
    confidence: float           # from ConfidenceEngine
    risk_level: str             # "low" / "medium" / "high"
    reasoning: str              # human-readable explanation


class PositionSizer:
    """Calculate position size based on risk management rules."""

    DEFAULT_RISK_PER_TRADE = 0.02   # 2% of portfolio per trade
    MAX_SINGLE_POSITION = 0.20      # max 20% in one stock
    MIN_POSITION = 0.03             # min 3% to be meaningful

    def calculate(
        self,
        *,
        portfolio_value: float,     # total portfolio value
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        atr_14: float,
        confidence: float,          # 0-100 from ConfidenceEngine
        market_regime: str,         # "进攻" / "均衡" / "防守"
    ) -> PositionAdvice:
        """Calculate position size.

        Method: Fixed Fractional Risk
        position_value = (risk_per_trade × portfolio × confidence_scale) / risk_per_share
        risk_per_share = entry_price - stop_loss_price

        Regime adjustments:
        - 进攻: max position = 20%
        - 均衡: max position = 15%
        - 防守: max position = 10%
        """
        ...
```

### 2.1 集成点

#### [MODIFY] `src/schemas/report_schema.py`

```python
class SniperPoints:
    """Sniper points (ideal_buy, stop_loss, etc.)."""
    # ... existing fields ...

    # Phase 2: position advice
    position_pct: Optional[float] = None
    risk_amount: Optional[float] = None
    profit_loss_ratio: Optional[str] = None
    confidence: Optional[float] = None
```

#### [MODIFY] `src/agent/executor.py`

Agent 输出格式中 `sniper_points` 新增 position 相关字段。

---

## 3. 多因子综合评分

#### [NEW] `src/core/multi_factor_scorer.py`

```python
"""Multi-factor composite scoring engine.

Combines technical, fundamental, money-flow, and market factors
into a single 0-100 score.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FactorScores:
    """Breakdown of multi-factor composite score."""
    technical: float        # 0-40
    fundamental: float      # 0-30 (requires Tushare)
    money_flow: float       # 0-20 (requires Tushare 6000)
    market: float           # 0-10
    total: float            # 0-100
    label: str              # "强烈推荐" / "推荐买入" / ...


class MultiFactorScorer:
    """Compute multi-factor composite scores."""

    def score(
        self,
        *,
        trend_result,          # TrendAnalysisResult
        fundamental_data=None, # Dict from Tushare fina_indicator (optional)
        money_flow_data=None,  # Dict from Tushare moneyflow (optional)
        market_regime: str = "均衡",
    ) -> FactorScores:
        """Compute composite score.

        Technical (0-40):
        - Trend strength (0-15): based on trend_status + ma_alignment
        - Volume-price harmony (0-10): volume confirms price direction
        - Indicator resonance (0-10): MACD/RSI/KDJ directional agreement
        - Pattern score (0-5): support/breakout patterns

        Fundamental (0-30, requires Tushare data):
        - ROE quality (0-10): ROE > 15% and stable
        - Valuation (0-10): PE/PB relative to sector median
        - Cash flow health (0-10): operating CF > net income

        Money Flow (0-20, requires Tushare 6000):
        - Institutional net inflow (0-10)
        - Chip concentration (0-10)

        Market (0-10):
        - Sector strength (0-5)
        - Index resonance (0-5)
        """
        technical = self._score_technical(trend_result)
        fundamental = self._score_fundamental(fundamental_data)
        money_flow = self._score_money_flow(money_flow_data)
        market = self._score_market(market_regime)

        total = technical + fundamental + money_flow + market
        label = self._get_label(total)

        return FactorScores(
            technical=technical,
            fundamental=fundamental,
            money_flow=money_flow,
            market=market,
            total=total,
            label=label,
        )

    def _score_technical(self, trend_result) -> float:
        """Technical factor scoring (0-40)."""
        score = 0.0

        # 1. Trend strength (0-15)
        ts = trend_result.trend_status
        trend_map = {
            "强势多头": 15, "多头排列": 12, "弱势多头": 8,
            "盘整": 5, "弱势空头": 3, "空头排列": 1, "强势空头": 0,
        }
        score += trend_map.get(ts.value if hasattr(ts, 'value') else str(ts), 5)

        # 2. Volume-price harmony (0-10)
        vs = trend_result.volume_status
        vp_map = {
            "放量上涨": 10, "缩量回调": 8, "量能正常": 5,
            "缩量上涨": 4, "放量下跌": 1,
        }
        score += vp_map.get(vs.value if hasattr(vs, 'value') else str(vs), 5)

        # 3. Indicator resonance (0-10)
        resonance = 0
        # MACD bullish
        if trend_result.macd_bar > 0:
            resonance += 3
        # RSI not overbought
        if 30 < trend_result.rsi_12 < 70:
            resonance += 3
        elif trend_result.rsi_12 <= 30:
            resonance += 4  # oversold bounce potential
        # KDJ signal
        if trend_result.kdj_signal == "golden_cross":
            resonance += 4
        elif trend_result.kdj_signal == "neutral":
            resonance += 2
        score += min(resonance, 10)

        # 4. Pattern score (0-5)
        if trend_result.support_ma5:
            score += 2
        if trend_result.support_ma10:
            score += 1.5
        if abs(trend_result.bias_ma5) < 2:
            score += 1.5

        return min(score, 40.0)

    def _score_fundamental(self, data) -> float:
        """Fundamental factor scoring (0-30). Returns 15 if no data."""
        if data is None:
            return 15.0  # neutral default when no fundamental data
        ...

    def _score_money_flow(self, data) -> float:
        """Money flow factor scoring (0-20). Returns 10 if no data."""
        if data is None:
            return 10.0  # neutral default when no money flow data
        ...

    def _score_market(self, market_regime: str) -> float:
        """Market environment scoring (0-10)."""
        regime_map = {"进攻": 9, "均衡": 5, "防守": 2}
        return regime_map.get(market_regime, 5)

    @staticmethod
    def _get_label(total: float) -> str:
        if total >= 85: return "强烈推荐"
        if total >= 70: return "推荐买入"
        if total >= 55: return "可以关注"
        if total >= 40: return "中性观望"
        return "建议回避"
```

### 3.1 数据降级策略

| 数据源 | 有数据时 | 无数据时 |
| --- | --- | --- |
| 技术面（TrendAnalysisResult） | 0-40 分评估 | **不可能无数据**（核心指标） |
| 基本面（Tushare fina_indicator） | 0-30 分评估 | **给中性分 15 分** |
| 资金面（Tushare moneyflow） | 0-20 分评估 | **给中性分 10 分** |
| 市场面（MarketBlueprint） | 0-10 分评估 | **给 5 分** |

> 降级后：满分 = 40(技术) + 15(基本面默认) + 10(资金面默认) + 5(市场面) = 70 分
> 评分标签 = "推荐买入"，这意味着不购买 Tushare 数据不影响系统可用，但精度有限。

### 3.2 集成点

#### [MODIFY] `src/services/analysis_service.py`

```python
# After agent analysis completes:
from src.core.multi_factor_scorer import MultiFactorScorer

scorer = MultiFactorScorer()
factor_scores = scorer.score(
    trend_result=trend_analysis_result,
    fundamental_data=fundamental_data,  # from Tushare or None
    money_flow_data=money_flow_data,    # from Tushare or None
    market_regime=current_market_regime,
)
# Write to report
```

#### [MODIFY] `src/storage.py` — AnalysisHistory 表

新增字段：

```python
# Multi-factor composite score
composite_score = Column(Float)         # 0-100
composite_label = Column(String(20))    # "强烈推荐" / ...
technical_score = Column(Float)         # 0-40
fundamental_score = Column(Float)       # 0-30
money_flow_score = Column(Float)        # 0-20
market_score = Column(Float)            # 0-10

# Position advice
position_pct = Column(Float)
confidence_score = Column(Float)        # 0-100
```

---

## 4. API 变更

#### [MODIFY] `api/v1/schemas/analysis.py`

报告 response schema 新增：

```python
class CompositeScore(BaseModel):
    total: float
    technical: float
    fundamental: float
    money_flow: float = Field(alias="moneyFlow")
    market: float
    label: str
    confidence: float

class PositionAdvice(BaseModel):
    position_pct: float = Field(alias="positionPct")
    risk_amount: float = Field(alias="riskAmount")
    profit_loss_ratio: str = Field(alias="profitLossRatio")
    confidence: float
```

#### [MODIFY] `api/v1/endpoints/history.py`

历史详情接口返回 `composite_score` 和 `position_advice`。

---

## 5. 前端 Phase 2 改动

#### [NEW] `apps/dsa-web/src/components/report/CompositeScoreGauge.tsx`

综合评分仪表盘（复用 ScoreGauge 弧线 + FactorBar 进度条）。

#### [NEW] `apps/dsa-web/src/components/report/PositionCard.tsx`

仓位建议卡片（4 个 StrategyItem 风格项）。

#### [NEW] `apps/dsa-web/src/components/common/ConfidenceBadge.tsx`

操作建议后的置信度标签。

#### [MODIFY] `apps/dsa-web/src/components/report/ReportOverview.tsx`

右侧区域改为双 gauge 布局（情绪 + 综合评分）。

#### [MODIFY] `apps/dsa-web/src/components/report/ReportStrategy.tsx`

狙击点位下方新增 PositionCard。

#### [MODIFY] `apps/dsa-web/src/types/analysis.ts`

新增 `CompositeScore` 和 `PositionAdvice` 类型。

---

## 6. 测试计划

### 6.1 单元测试

#### [NEW] `tests/test_confidence_engine.py`

覆盖：
- 回测数据映射到 base_score
- 市场环境修正系数验证
- 策略共振加权计算
- 信号衰减机制
- 边界值：win_rate=0, win_rate=100

#### [NEW] `tests/test_position_sizer.py`

覆盖：
- ATR 止损仓位计算
- 置信度缩放
- 市场模式限仓
- 极端值：stop_loss = entry_price, atr = 0

#### [NEW] `tests/test_multi_factor_scorer.py`

覆盖：
- 全因子评分
- 无基本面数据降级
- 无资金面数据降级
- 评分标签映射
- 各技术面子因子独立验证

### 6.2 集成验证

```bash
# Syntax check all new files
python -m py_compile src/core/confidence_engine.py
python -m py_compile src/core/position_sizer.py
python -m py_compile src/core/multi_factor_scorer.py

# Run all Phase 2 tests
python -m pytest tests/test_confidence_engine.py tests/test_position_sizer.py tests/test_multi_factor_scorer.py -v

# Verify no regression on existing tests
python -m pytest tests/ -x --timeout=60
```

### 6.3 前端构建

```bash
# vite.config.ts 已使用 loadEnv() 读取 .env.production，无需手动设置环境变量
cd apps/dsa-web && npm run build
# Verify no TS errors and components render correctly
```

---

## 7. 文件变更清单

| 操作 | 文件路径 | 说明 |
| --- | --- | --- |
| NEW | `src/core/confidence_engine.py` | 置信度计算引擎 |
| NEW | `src/core/position_sizer.py` | 仓位管理模型 |
| NEW | `src/core/multi_factor_scorer.py` | 多因子评分引擎 |
| NEW | `tests/test_confidence_engine.py` | 置信度测试 |
| NEW | `tests/test_position_sizer.py` | 仓位测试 |
| NEW | `tests/test_multi_factor_scorer.py` | 多因子测试 |
| NEW | `apps/dsa-web/src/components/report/CompositeScoreGauge.tsx` | 综合评分组件 |
| NEW | `apps/dsa-web/src/components/report/PositionCard.tsx` | 仓位建议组件 |
| NEW | `apps/dsa-web/src/components/common/ConfidenceBadge.tsx` | 置信度标签 |
| MODIFY | `src/storage.py` | AnalysisHistory 新增评分字段 |
| MODIFY | `src/services/analysis_service.py` | 集成评分和置信度 |
| MODIFY | `src/schemas/report_schema.py` | 报告结构新增字段 |
| MODIFY | `src/agent/executor.py` | Agent 输出新增字段 |
| MODIFY | `api/v1/schemas/analysis.py` | API schema 新增 |
| MODIFY | `api/v1/endpoints/history.py` | 返回评分数据 |
| MODIFY | `apps/dsa-web/src/components/report/ReportOverview.tsx` | 双 gauge 布局 |
| MODIFY | `apps/dsa-web/src/components/report/ReportStrategy.tsx` | 新增 PositionCard |
| MODIFY | `apps/dsa-web/src/types/analysis.ts` | 新增类型定义 |
