# Phase 1 开发文档：策略级回测 + 信号跟踪闭环

> 本阶段目标：让系统从"混合回测"升级为"每个策略独立可衡量"，并建立信号跟踪闭环。
> 预计工期：4-6 周（后端为主，前端仅 P1 优先级改动）

---

## 1. 策略 YAML 新增 quantitative_rules 字段

### 1.1 变更范围

#### [MODIFY] `src/agent/skills/base.py`

在 `Skill` dataclass 中新增字段：

```python
@dataclass
class Skill:
    # ... existing fields ...

    # Phase 1: quantitative backtesting rules
    quantitative_rules: Optional[Dict[str, Any]] = None
```

在 `load_skill_from_yaml()` 中读取新字段：

```python
quantitative_rules=data.get("quantitative_rules"),
```

#### [MODIFY] 策略 YAML 文件（全部 17 个）

每个 YAML 新增 `quantitative_rules` 块。买入/卖出条件使用结构化格式，
指标名称必须匹配 `TrendAnalysisResult` 的字段名。

**核心规则**：
- `indicator`：必须是 `TrendAnalysisResult` 的字段名（见 `src/stock_analyzer.py:83-157`）
- `operator`：`<`, `<=`, `>`, `>=`, `==`, `!=`, `in`, `not_in`, `between`
- `value`：数值、字符串或列表
- 条件之间默认 AND 关系

**示例 — `kdj_rsi_oversold.yaml`**：

```yaml
quantitative_rules:
  buy_conditions:
    - indicator: rsi_12
      operator: "<"
      value: 30
    - indicator: kdj_signal
      operator: "=="
      value: "golden_cross"
    - indicator: kdj_k
      operator: "<"
      value: 30
    - indicator: ma20_direction
      operator: "=="
      value: "上行"
  sell_conditions:
    - indicator: rsi_12
      operator: ">"
      value: 70
    - indicator: kdj_signal
      operator: "=="
      value: "dead_cross"
  holding_days: 10
  stop_loss_atr_multiple: 2.0
  take_profit_atr_multiple: 3.0
```

**示例 — `shrink_pullback.yaml`**：

```yaml
quantitative_rules:
  buy_conditions:
    - indicator: trend_status
      operator: "in"
      value: ["强势多头", "多头排列"]
    - indicator: bias_ma5
      operator: "between"
      value: [-2.0, 2.0]
    - indicator: volume_ratio_5d
      operator: "<"
      value: 0.7
    - indicator: support_ma5
      operator: "=="
      value: true
  sell_conditions:
    - indicator: trend_status
      operator: "in"
      value: ["空头排列", "强势空头"]
    - indicator: bias_ma5
      operator: ">"
      value: 5.0
  holding_days: 10
  stop_loss_atr_multiple: 2.0
  take_profit_atr_multiple: 2.5
```

**示例 — `bull_trend.yaml`**：

```yaml
quantitative_rules:
  buy_conditions:
    - indicator: trend_status
      operator: "in"
      value: ["强势多头", "多头排列"]
    - indicator: volume_status
      operator: "in"
      value: ["放量上涨", "量能正常"]
    - indicator: macd_status
      operator: "in"
      value: ["BULLISH", "GOLDEN_CROSS"]
    - indicator: bias_ma5
      operator: "<"
      value: 3.0
  sell_conditions:
    - indicator: trend_status
      operator: "in"
      value: ["弱势空头", "空头排列", "强势空头"]
    - indicator: macd_status
      operator: "=="
      value: "DEAD_CROSS"
  holding_days: 15
  stop_loss_atr_multiple: 2.0
  take_profit_atr_multiple: 3.0
```

**所有 17 个策略的 quantitative_rules 定义清单**：

| 策略 | 核心买入指标 | 核心卖出指标 | holding_days |
| --- | --- | --- | --- |
| bull_trend | trend_status=多头, macd=BULLISH, bias_ma5<3 | trend_status=空头, macd=DEAD_CROSS | 15 |
| shrink_pullback | trend_status=多头, bias_ma5∈[-2,2], vol_ratio<0.7 | trend=空头, bias_ma5>5 | 10 |
| kdj_rsi_oversold | rsi_12<30, kdj=golden_cross, kdj_k<30 | rsi_12>70, kdj=dead_cross | 10 |
| ma_convergence_breakout | trend_strength<30, ma5≈ma10≈ma20, vol>1.5 | 同上 | 10 |
| volume_breakout | vol_ratio>2.0, trend=多头, macd>0 | vol下降, trend转弱 | 8 |
| one_yang_three_yin | 特殊K线形态（需额外字段） | 跌破起涨K线最低价 | 5 |
| atr_squeeze_breakout | atr_trend=收缩, atr_ratio低位, 突破 | atr_ratio恢复高位 | 8 |
| ma_golden_cross | MA金叉+量能配合 | MA死叉 | 15 |
| bottom_volume | trend=空头→底量, vol极低, rsi超卖 | 反弹后量能萎缩 | 10 |
| box_oscillation | 在箱体下沿, rsi<40, 缩量 | 在箱体上沿, rsi>60 | 8 |
| wave_theory | 按波浪计数（复杂） | 按波浪计数 | 15 |
| dragon_head | 龙头股特征（需额外数据） | **降级处理** | 5 |
| emotion_cycle | 情绪周期（需额外数据） | **降级处理** | 10 |
| chan_theory | 缠论中枢（复杂） | **降级处理** | 15 |
| quality_factor | 基本面（需Tushare） | **暂不实现** | 20 |
| sector_rotation | 板块轮动（需Tushare） | **暂不实现** | 15 |
| fund_flow_driven | 资金流向（需Tushare） | **暂不实现** | 10 |

> 标注 **降级处理** 的策略：其买卖条件过于复杂或依赖无法量化的数据，
> Phase 1 中只实现简化版条件并标注 `backtestable: false`，不参与自动回测排名。

---

### 1.2 条件评估引擎

#### [NEW] `src/core/rule_evaluator.py`

```python
"""Evaluate quantitative_rules conditions against TrendAnalysisResult."""

from typing import Any, Dict, List, Optional
from dataclasses import asdict


class ConditionResult:
    """Single condition evaluation result."""
    def __init__(self, indicator: str, operator: str, expected: Any,
                 actual: Any, passed: bool):
        self.indicator = indicator
        self.operator = operator
        self.expected = expected
        self.actual = actual
        self.passed = passed


class RuleEvaluator:
    """Evaluate structured buy/sell conditions against indicator data."""

    OPERATORS = {
        "<": lambda a, b: a is not None and a < b,
        "<=": lambda a, b: a is not None and a <= b,
        ">": lambda a, b: a is not None and a > b,
        ">=": lambda a, b: a is not None and a >= b,
        "==": lambda a, b: a is not None and _eq(a, b),
        "!=": lambda a, b: a is not None and not _eq(a, b),
        "in": lambda a, b: a is not None and _str(a) in [_str(x) for x in b],
        "not_in": lambda a, b: a is not None and _str(a) not in [_str(x) for x in b],
        "between": lambda a, b: a is not None and len(b) == 2 and b[0] <= a <= b[1],
    }

    @classmethod
    def evaluate_conditions(
        cls,
        conditions: List[Dict[str, Any]],
        indicator_data: Dict[str, Any],
    ) -> tuple[bool, List[ConditionResult]]:
        """Evaluate all conditions (AND logic). Returns (all_passed, details)."""
        results = []
        for cond in conditions:
            indicator = cond["indicator"]
            operator = cond["operator"]
            expected = cond["value"]
            actual = indicator_data.get(indicator)

            op_fn = cls.OPERATORS.get(operator)
            if op_fn is None:
                passed = False
            else:
                try:
                    passed = op_fn(actual, expected)
                except (TypeError, ValueError):
                    passed = False

            results.append(ConditionResult(
                indicator=indicator, operator=operator,
                expected=expected, actual=actual, passed=passed,
            ))

        all_passed = all(r.passed for r in results)
        return all_passed, results

    @classmethod
    def evaluate_from_trend_result(
        cls,
        conditions: List[Dict[str, Any]],
        trend_result,  # TrendAnalysisResult
    ) -> tuple[bool, List[ConditionResult]]:
        """Convenience: convert TrendAnalysisResult to dict, then evaluate."""
        data = trend_result.to_dict()
        return cls.evaluate_conditions(conditions, data)
```

**辅助函数**：
```python
def _eq(a, b):
    """Flexible equality: handles enum.value vs string comparison."""
    if hasattr(a, 'value'):
        a = a.value
    return str(a) == str(b)

def _str(x):
    if hasattr(x, 'value'):
        return x.value
    return str(x)
```

---

## 2. 策略级回测引擎

#### [NEW] `src/core/strategy_backtester.py`

```python
"""Strategy-level backtester.

Scans historical daily data, applies quantitative_rules from each strategy
YAML, generates buy/sell signals, and evaluates each signal using the
existing BacktestEngine.
"""

@dataclass
class StrategySignal:
    """A signal generated by a strategy on a specific date."""
    strategy_name: str
    code: str
    signal_date: date
    direction: str  # "buy" or "sell"
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    conditions_met: List[ConditionResult]


@dataclass
class StrategyBacktestResult:
    """Aggregated backtest result for one strategy."""
    strategy_name: str
    total_signals: int
    win_count: int
    loss_count: int
    neutral_count: int
    win_rate: Optional[float]
    avg_return_pct: Optional[float]
    max_drawdown_pct: Optional[float]
    profit_factor: Optional[float]
    sharpe_ratio: Optional[float]
    avg_holding_days: Optional[float]
    stop_loss_trigger_rate: Optional[float]


class StrategyBacktester:
    """Backtest a single strategy against historical data."""

    def __init__(self, stock_analyzer, backtest_engine_config: EvaluationConfig):
        self.analyzer = stock_analyzer
        self.config = backtest_engine_config

    def scan_signals(
        self,
        strategy: Skill,
        code: str,
        df: pd.DataFrame,  # daily OHLCV data
    ) -> List[StrategySignal]:
        """Scan historical data for buy signals matching strategy rules.

        For each trading day:
        1. Calculate TrendAnalysisResult (MA/MACD/RSI/KDJ/ATR)
        2. Evaluate buy_conditions from quantitative_rules
        3. If all conditions met → generate StrategySignal
        """
        ...

    def evaluate_signals(
        self,
        signals: List[StrategySignal],
        df: pd.DataFrame,
    ) -> StrategyBacktestResult:
        """Evaluate each signal using BacktestEngine.evaluate_single().

        For each signal:
        - entry_price = close price on signal_date
        - stop_loss/take_profit from ATR multiples
        - forward_bars from subsequent daily data
        - Aggregate into StrategyBacktestResult
        """
        ...

    def backtest_strategy(
        self,
        strategy: Skill,
        code: str,
        df: pd.DataFrame,
    ) -> StrategyBacktestResult:
        """Full pipeline: scan → evaluate → aggregate."""
        signals = self.scan_signals(strategy, code, df)
        return self.evaluate_signals(signals, df)
```

**关键实现细节**：

1. **滑动窗口计算指标**：
   - 取 df 前 60 行作为预热数据
   - 从第 61 行开始逐日调用 `StockAnalyzer.analyze(df[:i])`
   - 每次得到完整的 `TrendAnalysisResult`

2. **信号去重**：
   - 同一策略对同一股票，买入信号后 `holding_days` 天内不再生成新信号
   - 如果在 holding_days 内触发卖出条件，记录卖出日期

3. **止损止盈计算**：
   - `stop_loss = entry_price - atr_14 * stop_loss_atr_multiple`
   - `take_profit = entry_price + atr_14 * take_profit_atr_multiple`

---

## 3. 策略回测服务层

#### [NEW] `src/services/strategy_backtest_service.py`

```python
class StrategyBacktestService:
    """Orchestrate strategy-level backtests and persist results."""

    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager.get_instance()
        self.repo = StrategyBacktestRepository(self.db)

    def run_strategy_backtest(
        self,
        strategy_name: Optional[str] = None,
        code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit_stocks: int = 50,
    ) -> Dict[str, Any]:
        """Run strategy backtest on historical data.

        If strategy_name is None: run all backtestable strategies.
        If code is None: use stocks from analysis_history.
        """
        ...

    def get_strategy_ranking(self) -> List[Dict[str, Any]]:
        """Return all strategies ranked by win_rate descending."""
        ...

    def update_confidence_weights(self) -> Dict[str, float]:
        """Auto-update confidence_weight based on backtest results.

        Formula:
        new_weight = 0.5 * backtest_win_rate + 0.3 * profit_factor_norm + 0.2 * sharpe_norm
        Clamped to [0.3, 0.98]
        """
        ...
```

---

## 4. 数据库变更

#### [MODIFY] `src/storage.py`

新增 2 张表：

```python
class StrategyBacktestSignal(Base):
    """Individual signal generated by a strategy during backtesting."""
    __tablename__ = 'strategy_backtest_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    code = Column(String(10), nullable=False, index=True)
    signal_date = Column(Date, nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # buy/sell
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)

    # Evaluation results (filled after backtest)
    eval_status = Column(String(16), default='pending')
    outcome = Column(String(16))  # win/loss/neutral
    return_pct = Column(Float)
    exit_reason = Column(String(24))
    holding_days = Column(Integer)

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('ix_strat_signal_name_code', 'strategy_name', 'code'),
        UniqueConstraint('strategy_name', 'code', 'signal_date',
                         name='uix_strat_signal_unique'),
    )


class StrategyBacktestSummary(Base):
    """Aggregated backtest results per strategy."""
    __tablename__ = 'strategy_backtest_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(50), nullable=False, unique=True, index=True)
    total_signals = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    win_rate_pct = Column(Float)
    avg_return_pct = Column(Float)
    max_drawdown_pct = Column(Float)
    profit_factor = Column(Float)
    sharpe_ratio = Column(Float)
    avg_holding_days = Column(Float)
    stop_loss_trigger_rate = Column(Float)
    # Auto-computed confidence score
    computed_confidence = Column(Float)
    computed_at = Column(DateTime, default=datetime.now)
```

#### [NEW] `src/repositories/strategy_backtest_repo.py`

```python
class StrategyBacktestRepository:
    """Repository for strategy backtest signals and summaries."""

    def save_signals_batch(self, signals: List[StrategyBacktestSignal]) -> int: ...
    def get_signals(self, strategy_name: str, code: str = None) -> List: ...
    def upsert_summary(self, summary: StrategyBacktestSummary) -> None: ...
    def get_all_summaries(self) -> List[StrategyBacktestSummary]: ...
    def get_summary(self, strategy_name: str) -> Optional[StrategyBacktestSummary]: ...
```

---

## 5. 信号跟踪系统

#### [NEW] `src/core/signal_tracker.py`

```python
class SignalTracker:
    """Track live signals from analysis reports.

    When the system generates an analysis report with operation_advice = "买入":
    1. Create a Signal record with entry_price, stop_loss, take_profit
    2. Daily cron: check if stop_loss or take_profit was hit
    3. After holding_days: auto-close signal and compute return
    """
    ...
```

#### [MODIFY] `src/storage.py`

新增信号跟踪表：

```python
class Signal(Base):
    """Live signal tracking."""
    __tablename__ = 'signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_history_id = Column(Integer, ForeignKey('analysis_history.id'), index=True)
    code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50))

    # Signal details
    strategy_name = Column(String(50))  # which strategy triggered this
    direction = Column(String(8), nullable=False)  # long/cash
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    position_pct = Column(Float)  # suggested position %
    confidence = Column(Float)    # signal confidence score

    # Lifecycle
    status = Column(String(16), default='pending', index=True)
    # pending → active → take_profit/stop_loss/expired
    created_at = Column(DateTime, default=datetime.now, index=True)
    closed_at = Column(DateTime)
    current_price = Column(Float)  # last updated price
    return_pct = Column(Float)     # realized or unrealized return

    # Expiry
    holding_days = Column(Integer, default=10)
    expire_date = Column(Date)

    __table_args__ = (
        Index('ix_signal_status_date', 'status', 'created_at'),
    )
```

#### [NEW] `src/services/signal_service.py`

```python
class SignalService:
    """Manage signal lifecycle."""

    def create_signal_from_report(self, analysis_history_id: int) -> Optional[Signal]:
        """Extract signal info from analysis report and create Signal record."""
        ...

    def update_active_signals(self) -> Dict[str, int]:
        """Daily job: update prices and check stop_loss/take_profit."""
        ...

    def get_active_signals(self, page=1, limit=20) -> Dict[str, Any]:
        """Paginated list of active signals."""
        ...

    def get_signal_summary(self) -> Dict[str, Any]:
        """Aggregate signal performance summary."""
        ...

    def close_expired_signals(self) -> int:
        """Close signals past their holding_days."""
        ...
```

---

## 6. API 新增接口

#### [NEW] `api/v1/endpoints/signals.py`

```python
router = APIRouter()

@router.get("/")           # GET /api/v1/signals — signal list (paginated)
@router.get("/summary")    # GET /api/v1/signals/summary — performance summary
@router.get("/{signal_id}")  # GET /api/v1/signals/:id — signal detail
```

#### [MODIFY] `api/v1/endpoints/backtest.py`

新增策略维度回测接口：

```python
@router.get("/strategy-summary")  # GET /api/v1/backtest/strategy-summary
@router.post("/strategy-run")     # POST /api/v1/backtest/strategy-run
```

#### [NEW] `api/v1/schemas/signals.py`

Pydantic schemas for Signal API responses.

#### [MODIFY] `api/v1/schemas/backtest.py`

新增 `StrategyPerformanceItem` schema.

---

## 7. 前端 Phase 1 改动

#### [NEW] `apps/dsa-web/src/pages/SignalsPage.tsx`

信号看板页面（参照 gap analysis 6.3 节设计）。

#### [NEW] `apps/dsa-web/src/api/signals.ts`

Signals API client（对应后端接口）。

#### [NEW] `apps/dsa-web/src/types/signals.ts`

TypeScript 类型定义（SignalItem, SignalSummary）。

#### [MODIFY] `apps/dsa-web/src/App.tsx`

- NAV_ITEMS 新增 信号 entry
- Routes 新增 `/signals` → `<SignalsPage/>`

#### [MODIFY] `apps/dsa-web/src/pages/BacktestPage.tsx`

- 左侧新增 `StrategyPerformanceCard`
- 表格新增 `strategy` 列

---

## 8. 测试计划

### 8.1 单元测试

#### [NEW] `tests/test_rule_evaluator.py`

```bash
python -m pytest tests/test_rule_evaluator.py -v
```

覆盖：
- 所有 9 种 operator 的正向/反向测试
- Enum value vs string 比较
- None 值处理
- `between` 边界值

#### [NEW] `tests/test_strategy_backtester.py`

```bash
python -m pytest tests/test_strategy_backtester.py -v
```

覆盖：
- 合成日线数据生成买入信号
- 信号去重（holding_days 冷却期）
- ATR 止损止盈计算
- 回测结果汇总（胜率/盈亏比/回撤）

#### [MODIFY] 运行已有回测测试确认无回归

```bash
python -m pytest tests/test_backtest_engine.py tests/test_backtest_service.py tests/test_backtest_summary.py -v
```

### 8.2 集成测试

#### 语法检查

```bash
python -m py_compile src/core/rule_evaluator.py
python -m py_compile src/core/strategy_backtester.py
python -m py_compile src/services/strategy_backtest_service.py
python -m py_compile src/services/signal_service.py
python -m py_compile src/core/signal_tracker.py
```

#### API 端到端测试

```bash
# Start dev server
python -m uvicorn api.main:app --host 0.0.0.0 --port 8888 &

# Test signal endpoints
curl -s http://localhost:8888/api/v1/signals | python -m json.tool
curl -s http://localhost:8888/api/v1/signals/summary | python -m json.tool

# Test strategy backtest
curl -X POST http://localhost:8888/api/v1/backtest/strategy-run \
  -H 'Content-Type: application/json' \
  -d '{"strategy_name": "kdj_rsi_oversold", "limit_stocks": 5}'

curl -s http://localhost:8888/api/v1/backtest/strategy-summary | python -m json.tool
```

### 8.3 前端验证

```bash
cd apps/dsa-web && npm run build
```

验证无 TypeScript 编译错误，信号看板页面可正常渲染。

---

## 9. 文件变更清单

| 操作 | 文件路径 | 说明 |
| --- | --- | --- |
| NEW | `src/core/rule_evaluator.py` | 条件评估引擎 |
| NEW | `src/core/strategy_backtester.py` | 策略级回测引擎 |
| NEW | `src/core/signal_tracker.py` | 信号跟踪核心逻辑 |
| NEW | `src/services/strategy_backtest_service.py` | 策略回测服务编排 |
| NEW | `src/services/signal_service.py` | 信号生命周期管理 |
| NEW | `src/repositories/strategy_backtest_repo.py` | 策略回测数据仓库 |
| NEW | `api/v1/endpoints/signals.py` | 信号 API 接口 |
| NEW | `api/v1/schemas/signals.py` | 信号 API 数据模型 |
| NEW | `tests/test_rule_evaluator.py` | 条件评估单元测试 |
| NEW | `tests/test_strategy_backtester.py` | 策略回测单元测试 |
| NEW | `apps/dsa-web/src/pages/SignalsPage.tsx` | 信号看板页面 |
| NEW | `apps/dsa-web/src/api/signals.ts` | 信号 API 客户端 |
| NEW | `apps/dsa-web/src/types/signals.ts` | 信号类型定义 |
| MODIFY | `src/agent/skills/base.py` | Skill 新增 quantitative_rules |
| MODIFY | `src/storage.py` | 新增 3 张表 |
| MODIFY | `strategies/*.yaml` × 17 | 全部新增 quantitative_rules |
| MODIFY | `api/v1/endpoints/backtest.py` | 新增策略维度接口 |
| MODIFY | `api/v1/schemas/backtest.py` | 新增策略回测 schema |
| MODIFY | `apps/dsa-web/src/App.tsx` | 导航栏新增信号 |
| MODIFY | `apps/dsa-web/src/pages/BacktestPage.tsx` | 策略绩效卡片 |
