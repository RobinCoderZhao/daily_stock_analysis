# Phase 3 开发文档：组合风控 + 前端 UI 集成 + 运维

> 本阶段目标：建立组合风控层，完成所有前端 UI 集成，实现自动化运维任务。
> 前置依赖：Phase 1 + Phase 2 全部完成
> 预计工期：3-4 周

---

## 1. 组合风控管理

### 1.1 风控管理器

#### [NEW] `src/core/portfolio_risk_manager.py`

```python
"""Portfolio risk management module.

Controls:
1. Total portfolio exposure limits
2. Sector concentration limits
3. Concurrent signal limits
4. Correlation-based risk scaling
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


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
    rejections: List[str]     # reasons if any position was reduced/rejected
    warnings: List[str]       # non-blocking warnings


class PortfolioRiskManager:
    """Check and adjust positions against portfolio-level risk rules."""

    def __init__(self, config: PortfolioConfig = None):
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

        Returns adjusted position or rejection with reasons.
        """
        rejections = []
        warnings = []
        adjusted = proposed_position_pct

        # 1. Check max concurrent signals
        if len(active_signals) >= self.config.max_concurrent_signals:
            rejections.append(
                f"已达最大持仓数 ({self.config.max_concurrent_signals})")
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )

        # 2. Check total exposure
        current_exposure = sum(s.get("position_pct", 0) for s in active_signals)
        remaining = self.config.max_total_exposure_pct - current_exposure
        if remaining <= 0:
            rejections.append(
                f"总仓位已满 ({current_exposure:.1f}%/{self.config.max_total_exposure_pct}%)")
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )
        if adjusted > remaining:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {remaining:.1f}% (总仓位上限)")
            adjusted = remaining

        # 3. Check single position cap
        if adjusted > self.config.max_single_position_pct:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {self.config.max_single_position_pct}% (单股上限)")
            adjusted = self.config.max_single_position_pct

        # 4. Check sector concentration
        sector_exposure = sum(
            s.get("position_pct", 0) for s in active_signals
            if s.get("sector") == sector
        )
        sector_remaining = self.config.max_sector_concentration_pct - sector_exposure
        if sector_remaining <= 0:
            rejections.append(
                f"{sector} 板块仓位已满 ({sector_exposure:.1f}%)")
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )
        if adjusted > sector_remaining:
            warnings.append(
                f"仓位从 {adjusted:.1f}% 调整为 {sector_remaining:.1f}% (板块上限)")
            adjusted = sector_remaining

        # 5. Daily signal count
        today_signals = [
            s for s in active_signals
            if s.get("created_today", False)
        ]
        if len(today_signals) >= self.config.max_daily_new_signals:
            rejections.append(
                f"今日新增信号已达上限 ({self.config.max_daily_new_signals}个)")
            return RiskCheckResult(
                approved=False, original_position_pct=proposed_position_pct,
                adjusted_position_pct=0, rejections=rejections, warnings=warnings,
            )

        return RiskCheckResult(
            approved=True, original_position_pct=proposed_position_pct,
            adjusted_position_pct=adjusted, rejections=rejections, warnings=warnings,
        )
```

### 1.2 风控配置持久化

#### [MODIFY] `src/services/system_config_service.py`

新增风控配置项（通过现有 system_config 接口管理）：

```python
PORTFOLIO_RISK_DEFAULTS = {
    "portfolio.max_total_exposure_pct": "60",
    "portfolio.max_single_position_pct": "20",
    "portfolio.max_sector_concentration_pct": "30",
    "portfolio.max_concurrent_signals": "8",
    "portfolio.max_daily_new_signals": "3",
    "portfolio.risk_per_trade_pct": "2.0",
    "portfolio.value": "100000",
}
```

用户可在设置页调整上述参数。

### 1.3 集成点

#### [MODIFY] `src/services/signal_service.py`

```python
# In create_signal_from_report():
risk_manager = PortfolioRiskManager(config)
risk_check = risk_manager.check_signal(
    code=code, sector=sector,
    proposed_position_pct=position_advice.position_pct,
    active_signals=self.get_active_signals_list(),
)
if not risk_check.approved:
    # Log rejection, still create signal but with status='risk_blocked'
    ...
else:
    signal.position_pct = risk_check.adjusted_position_pct
```

---

## 2. 自动化定时任务

#### [NEW] `src/jobs/signal_updater.py`

```python
"""Daily cron job for signal lifecycle management.

Should be registered in main scheduler (cron or APScheduler).
Runs:
1. Fetch current prices for active signals
2. Check stop_loss / take_profit triggers
3. Close expired signals
4. Compute and cache performance summaries
"""

class SignalUpdaterJob:
    def run(self):
        """Execute daily signal update cycle."""
        signal_service = SignalService()

        # Update prices and check triggers
        updates = signal_service.update_active_signals()
        logger.info(f"Signal update: {updates}")

        # Close expired signals
        expired_count = signal_service.close_expired_signals()
        logger.info(f"Closed {expired_count} expired signals")

        return {"updates": updates, "expired": expired_count}
```

#### [NEW] `src/jobs/strategy_backtest_scheduler.py`

```python
"""Weekly cron job for strategy backtesting.

Runs every Sunday at 22:00:
1. Run strategy-level backtests on recent data
2. Update strategy ranking
3. Optionally update confidence weights
"""

class StrategyBacktestSchedulerJob:
    def run(self):
        service = StrategyBacktestService()
        results = service.run_strategy_backtest(limit_stocks=30)
        service.update_confidence_weights()
        return results
```

#### [MODIFY] `main.py` 或调度入口

注册定时任务到 APScheduler 或 cron：

```python
# Daily at 16:00 CST (after market close)
scheduler.add_job(SignalUpdaterJob().run, 'cron', hour=16, minute=0)

# Weekly Sunday at 22:00 CST
scheduler.add_job(
    StrategyBacktestSchedulerJob().run,
    'cron', day_of_week='sun', hour=22, minute=0,
)
```

---

## 3. 前端 UI 完整集成

### 3.1 信号看板完善

#### [MODIFY] `apps/dsa-web/src/pages/SignalsPage.tsx`

Phase 1 中创建了基础结构，Phase 3 补全：

- **策略排行组件** (`StrategyRanking.tsx`)
  - 复用 `Card` + 内嵌进度条
  - 按胜率降序，标注 ≥60% 绿色、40-60% 黄色、<40% 红色 + 淘汰警告

- **月度绩效曲线** (`MonthlyPerfChart.tsx`)
  - 使用纯 SVG 实现折线图（不引入 recharts 库）
  - 数据来源：`GET /api/v1/signals/monthly-performance`
  - 鼠标 hover 显示具体月份数据

- **信号详情抽屉** (`SignalDetailDrawer.tsx`)
  - 复用现有 `Drawer` 组件
  - 展示信号完整生命周期：创建→活跃→止盈/止损/过期
  - 含置信度分解、条件匹配详情

### 3.2 设置页风控配置

#### [MODIFY] `apps/dsa-web/src/pages/SettingsPage.tsx`

新增"组合风控"设置区域：

```
┌── 组合风控设置 ─────────────────────────┐
│ 账户总值      [¥100,000 ]              │
│ 最大总仓位    [60     ]%               │
│ 单股上限      [20     ]%               │
│ 板块集中上限  [30     ]%               │
│ 最大持仓数    [8      ]               │
│ 每日新增上限  [3      ]               │
│ 单笔风险上限  [2.0    ]%               │
│                                        │
│               [保存设置]                 │
└────────────────────────────────────────┘
```

复用现有 `SettingsField` 组件。

### 3.3 回测页最终增强

#### [MODIFY] `apps/dsa-web/src/pages/BacktestPage.tsx`

- 新增 Tab 切换：`整体回测 | 策略回测`
- 策略回测 Tab 展示所有策略的 `StrategyPerformanceCard` 网格
- 可点击策略名查看该策略的信号明细

### 3.4 首页报告集成验证

确保 Phase 2 的组件在实际数据下正常工作：
- `CompositeScoreGauge` 动画流畅
- `PositionCard` 数据正确显示
- `ConfidenceBadge` 颜色映射正确
- 降级模式（无 Tushare 数据时）显示中性分

---

## 4. API 补充接口

#### [NEW] `api/v1/endpoints/signals.py` 补充

```python
@router.get("/monthly-performance")  # 月度绩效数据
@router.post("/{signal_id}/close")   # 手动关闭信号
```

#### [MODIFY] `api/v1/endpoints/system_config.py`

确保风控配置项可通过现有 system_config 接口读写。

---

## 5. 测试计划

### 5.1 单元测试

#### [NEW] `tests/test_portfolio_risk_manager.py`

覆盖：
- 正常建仓通过
- 超出总仓位限制 → 仓位调整
- 超出板块集中度 → 拒绝
- 超出最大持仓数 → 拒绝
- 今日限额已满 → 拒绝
- 空仓位列表 → 全部通过

#### [NEW] `tests/test_signal_updater.py`

覆盖：
- 价格更新逻辑
- 止损触发检测
- 止盈触发检测
- 过期信号关闭

### 5.2 集成验证

```bash
# Syntax
python -m py_compile src/core/portfolio_risk_manager.py
python -m py_compile src/jobs/signal_updater.py
python -m py_compile src/jobs/strategy_backtest_scheduler.py

# All unit tests
python -m pytest tests/ -x --timeout=60

# API test
curl -s http://localhost:8888/api/v1/signals/monthly-performance | python -m json.tool
```

### 5.3 前端端到端验证

```bash
cd apps/dsa-web && npm run build && npm run dev
```

浏览器验证清单：
1. ✅ 首页报告：双 gauge（情绪 + 综合评分）正常渲染
2. ✅ 首页报告：PositionCard 4 项数据正确
3. ✅ 首页报告：ConfidenceBadge 颜色正确
4. ✅ 信号看板：信号列表加载、筛选、分页
5. ✅ 信号看板：策略排行排序、颜色标注
6. ✅ 信号看板：月度绩效曲线渲染
7. ✅ 回测页：策略维度 Tab 切换
8. ✅ 设置页：风控配置读写成功
9. ✅ 移动端响应式：侧边栏折叠正常

---

## 6. 文件变更清单

| 操作 | 文件路径 | 说明 |
| --- | --- | --- |
| NEW | `src/core/portfolio_risk_manager.py` | 组合风控 |
| NEW | `src/jobs/signal_updater.py` | 信号更新定时任务 |
| NEW | `src/jobs/strategy_backtest_scheduler.py` | 策略回测定时任务 |
| NEW | `tests/test_portfolio_risk_manager.py` | 风控测试 |
| NEW | `tests/test_signal_updater.py` | 信号更新测试 |
| NEW | `apps/dsa-web/src/components/signals/StrategyRanking.tsx` | 策略排行 |
| NEW | `apps/dsa-web/src/components/signals/MonthlyPerfChart.tsx` | 绩效曲线 |
| NEW | `apps/dsa-web/src/components/signals/SignalDetailDrawer.tsx` | 信号详情 |
| MODIFY | `src/services/signal_service.py` | 集成风控检查 |
| MODIFY | `src/services/system_config_service.py` | 风控配置默认值 |
| MODIFY | `apps/dsa-web/src/pages/SignalsPage.tsx` | 补全完整功能 |
| MODIFY | `apps/dsa-web/src/pages/BacktestPage.tsx` | Tab 切换 |
| MODIFY | `apps/dsa-web/src/pages/SettingsPage.tsx` | 风控设置 |
| MODIFY | 调度入口（main.py 或 scheduler） | 注册定时任务 |

---

## 7. 三阶段总工期与里程碑

| 阶段 | 工期 | 里程碑 |
| --- | --- | --- |
| **Phase 1** | 4-6 周 | 策略可独立回测，信号可跟踪 |
| **Phase 2** | 3-4 周 | 每条建议有置信度+仓位+综合评分 |
| **Phase 3** | 3-4 周 | 组合风控上线，前端完整交付 |
| **总计** | **10-14 周** | 系统从研究工具升级为交易顾问 |

> [!IMPORTANT]
> Phase 1 是所有后续工作的基础。必须先完成 Phase 1 的 `RuleEvaluator` 和 `StrategyBacktester`，
> 才能为 Phase 2 的 `ConfidenceEngine` 提供数据，进而为 Phase 3 的风控提供输入。
> **严禁跳阶段开发。**
