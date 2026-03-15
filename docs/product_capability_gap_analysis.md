# 产品能力差距分析：从研究工具到交易顾问

> 目标：让系统从"技术面快速研究助手"升级为"可提供有数据支撑的交易策略建议的量化分析平台"

## 一、现有能力基线

### ✅ 已具备的能力

| 模块 | 当前状态 | 评估 |
| --- | --- | --- |
| **数据获取** | 6源自动降级（efinance/akshare/tushare/pytdx/baostock/yfinance） | 稳定可用 |
| **技术指标计算** | MA/MACD/RSI/KDJ/ATR/换手率/乖离率/MA斜率 | 覆盖面足够 |
| **LLM Agent 分析** | Agent + Tools + Skills (YAML策略) 架构 | 灵活可扩展 |
| **回测引擎** | `BacktestEngine` 支持单笔止盈止损评估、胜率/方向准确率统计 | **已有基础** |
| **回测服务** | `BacktestService` 批量回测 + DB持久化 + Summary聚合 | **已有框架** |
| **狙击点位** | ideal_buy / secondary_buy / stop_loss / take_profit | 已有结构 |
| **通知推送** | 邮件/Bark/微信推送 | 完善 |
| **WebUI** | React前端 + FastAPI后端 | 基础可用 |
| **市场复盘** | CN/US市场日度复盘策略蓝图 | 已有 |

### ❌ 缺失的关键能力

| 缺失能力 | 严重程度 | 对"可指导交易"的影响 |
| --- | --- | --- |
| 策略级独立回测 | 🔴 致命 | 不知道哪个策略真正赚钱 |
| 信号置信度量化 | 🔴 致命 | confidence_weight 是人为估计，非数据驱动 |
| 仓位管理模型 | 🟡 重要 | 只说"买/不买"，不说"买多少" |
| 组合风控 | 🟡 重要 | 无总仓位限制、行业集中度控制 |
| 策略表现看板 | 🟠 中等 | 无法可视化跟踪策略历史表现 |
| 信号跟踪闭环 | 🟠 中等 | 发出信号后无法追踪结果 |
| 多因子融合评分 | 🟡 重要 | 技术面/基本面/资金面各自独立，无综合打分 |

---

## 二、需要补全的六大能力模块

### 模块一：策略级独立回测系统（最高优先级 🔴）

**现状**：当前 `BacktestEngine` 回测的是 LLM 整体输出（operation_advice），无法区分"是哪个策略产生了这个建议"。

**问题**：
- 17个策略混在一起回测，无法知道 `bull_trend` 胜率是 60% 而 `wave_theory` 只有 40%
- 无法基于历史数据做策略淘汰和优化
- confidence_weight 没有数据支撑

**需要实现的**：

```
StrategyBacktester
├── 对每个策略 YAML 定义的买入条件做规则化解析
├── 在历史日线数据上逐日扫描，产生买卖信号
├── 对每个信号用 BacktestEngine 评估盈亏
├── 输出每个策略的独立统计：
│   ├── 胜率 (win_rate)
│   ├── 盈亏比 (profit_factor)
│   ├── 最大回撤 (max_drawdown)
│   ├── 夏普比率 (sharpe_ratio)
│   └── 平均持仓天数 (avg_holding_days)
└── 自动更新 YAML 中的 confidence_weight
```

**核心挑战**：当前策略 YAML 中的买入条件是自然语言描述（给 LLM 读的），需要转化为可编程的规则。两种路径：

- **路径 A（推荐）**：在 YAML 中新增 `quantitative_rules` 字段，用结构化方式定义条件
- **路径 B**：用 LLM 解析自然语言条件为 Python 表达式（不可靠，不推荐）

**示例 — 新增 quantitative_rules 字段**：

```yaml
name: kdj_rsi_oversold
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

---

### 模块二：信号置信度量化引擎（高优先级 🔴）

**现状**：confidence_weight 是人为设定的静态值（0.7-0.95），不会随市场变化。

**需要实现的**：

```
SignalConfidenceEngine
├── 基于回测的历史胜率/盈亏比计算基础置信度
├── 市场环境修正系数（牛市放大/熊市压缩）
├── 策略共振加权（多策略同时触发时提升置信度）
├── 信号衰减机制（同一信号连续出现时递减）
└── 最终输出 0-100 的综合置信分
```

**公式建议**：

```
confidence = base_score × market_modifier × resonance_bonus × decay_factor

其中：
- base_score = f(历史胜率, 盈亏比, 夏普比) — 来自模块一的回测结果
- market_modifier = f(大盘趋势, 成交量温度, VIX等价指标) — 0.5~1.5
- resonance_bonus = 1 + 0.1 × (同时触发的策略数 - 1) — 最高 1.5
- decay_factor = 1 / (1 + 近5日同策略触发次数) — 防止重复信号
```

---

### 模块三：仓位管理模型（中高优先级 🟡）

**现状**：系统只输出"买入/观望"，不告诉用户应该投入多少资金。

**需要实现的**：

```
PositionSizer
├── 基于 ATR 的固定风险仓位法
│   └── 仓位 = 账户风险金额 / (ATR × 止损ATR倍数)
├── 基于置信度的动态仓位调整
│   └── 仓位比例 = base_position × (confidence / 100)
├── 最大单票仓位限制（如不超过总资金20%）
└── 输出格式：建议仓位比例 + 建议手数 + 风险敞口
```

**对用户的价值**：从"你可以关注这只股票"升级为"你可以用总资金的15%买入，止损位XX元，风险敞口XX元"。

---

### 模块四：组合风控层（中等优先级 🟡）

**现状**：每只股票独立分析，没有组合层面的风险控制。

**需要实现的**：

```
PortfolioRiskManager
├── 总仓位上限（如当前市场环境最多 70% 仓位）
├── 单行业集中度限制（如单一行业不超过 30%）
├── 在手信号数量限制（如同时最多持有 5 只）
├── 相关性检查（不同时推荐高度相关的股票）
└── 风险等级映射
    ├── 进攻模式：满仓可用，信号分≥70即可推荐
    ├── 均衡模式：最多60%仓位，信号分≥80才推荐
    └── 防守模式：最多30%仓位，信号分≥90才推荐
```

---

### 模块五：信号跟踪与绩效闭环（中等优先级 🟠）

**现状**：系统发出分析报告后就"忘了"。没有跟踪这个信号后来是赚了还是亏了。

**需要实现的**：

```
SignalTracker
├── 信号发出后自动记录（股票/方向/入场价/止损/止盈/策略名）
├── 每日自动更新在途信号状态（未触发/已入场/止盈/止损/过期）
├── 信号到期后自动归档并计入回测统计
├── 提供"信号看板"接口：
│   ├── 当前活跃信号列表
│   ├── 近30天信号命中率
│   └── 不同策略的实时绩效排行
└── 定期报告（周/月绩效汇总通知）
```

**核心价值**：让用户能看到"上个月你推荐了 15 只股票，10 只盈利，3 只止损，2 只持平，总收益率 +8.3%"。

> [!IMPORTANT]
> 这是用户信任度的基础。没有绩效跟踪，用户不会信任系统的建议。

---

### 模块六：多因子融合评分（中等优先级 🟡）

**现状**：技术面指标丰富，但基本面和资金面数据各自独立，没有统一打分。

**需要实现的**：

```
MultiFactorScorer
├── 技术面评分 (0-40分)
│   ├── 趋势强度 (0-15)
│   ├── 量价配合 (0-10)
│   ├── 指标共振 (0-10)：MACD/RSI/KDJ 方向一致性
│   └── 形态得分 (0-5)：突破/支撑/压力
├── 基本面评分 (0-30分) — 需 Tushare 财务数据
│   ├── ROE质量 (0-10)
│   ├── 估值水平 (0-10)
│   └── 现金流健康度 (0-10)
├── 资金面评分 (0-20分) — 需 Tushare 资金流数据
│   ├── 主力净流入 (0-10)
│   └── 筹码集中度 (0-10)
├── 市场面评分 (0-10分)
│   └── 板块强度 + 大盘共振
└── 最终综合评分 = 技术面 + 基本面 + 资金面 + 市场面 (0-100)
```

**评分对应建议**：

| 综合评分 | 建议 | 仓位参考 |
| --- | --- | --- |
| 85-100 | 强烈推荐买入 | 15-20% |
| 70-84 | 推荐买入 | 10-15% |
| 55-69 | 可以关注 | 5-10% |
| 40-54 | 中性观望 | 0% |
| 0-39 | 建议回避 | 0% |

---

## 三、实施优先级路线图

### 第一阶段：建立可信度基础（4-6 周）

| 序号 | 任务 | 依赖 | 价值 |
| --- | --- | --- | --- |
| 1.1 | 在策略 YAML 中新增 `quantitative_rules` 字段 | 无 | 策略可回测的前提 |
| 1.2 | 实现 `StrategyBacktester` 批量历史回测 | 1.1 + 现有 BacktestEngine | **核心突破** |
| 1.3 | 基于回测结果自动更新 confidence_weight | 1.2 | 数据驱动的置信度 |
| 1.4 | 实现信号跟踪表 + 活跃信号看板 API | DB schema | 绩效可见 |
| 1.5 | 配置 Tushare Token（5000-6000 积分） | 账号注册 | 数据完整性 |

### 第二阶段：增加决策深度（3-4 周）

| 序号 | 任务 | 依赖 | 价值 |
| --- | --- | --- | --- |
| 2.1 | 实现 `SignalConfidenceEngine` 动态置信度 | 第一阶段 | 信号质量分层 |
| 2.2 | 实现 `PositionSizer` 基于 ATR 的仓位建议 | 现有 ATR 计算 | 可操作性提升 |
| 2.3 | 实现 `MultiFactorScorer` 多因子综合评分 | Tushare 数据 | 分析立体化 |
| 2.4 | 在分析报告中输出综合评分 + 仓位建议 | 2.2 + 2.3 | 用户体验升级 |

### 第三阶段：风控与运营闭环（2-3 周）

| 序号 | 任务 | 依赖 | 价值 |
| --- | --- | --- | --- |
| 3.1 | 实现 `PortfolioRiskManager` 组合风控 | 第二阶段 | 风险可控 |
| 3.2 | 周/月绩效报告自动生成与推送 | 信号跟踪 | 用户留存 |
| 3.3 | WebUI 策略绩效看板页面 | 回测数据API | 可视化 |
| 3.4 | 策略自动淘汰/降级机制 | 持续回测 | 系统自进化 |

---

## 四、成功衡量标准

系统要达到"可指导交易"的水平，至少需要满足：

| 指标 | 目标值 | 计算方式 |
| --- | --- | --- |
| **策略回测覆盖率** | 100% | 所有激活策略都有≥6个月的回测数据 |
| **信号跟踪闭环率** | ≥95% | 发出的信号都有最终盈亏记录 |
| **综合胜率** | ≥55% | 跟踪信号中盈利信号的占比 |
| **盈亏比** | ≥1.5:1 | 平均盈利金额 / 平均亏损金额 |
| **最大回撤** | ≤-15% | 组合模拟的最大回撤 |
| **每笔建议包含** | 6要素齐全 | 方向 + 入场价 + 止损 + 止盈 + 仓位 + 置信度 |

> [!CAUTION]
> 在上述指标未全部达标前，所有信号建议必须标注 **"仅供研究参考，不构成投资建议"** 的免责声明。

---

## 五、当前系统意外发现的优势

在分析过程中，发现系统已经有一些被低估的能力：

1. **BacktestEngine 已经很完整** — 止盈止损命中评估、方向准确率、模拟收益率计算、advice 分类统计都有了。不需要从零开始。
2. **BacktestService 已有批量回测 + 持久化** — 自动补全历史数据的逻辑也有了。
3. **狙击点位结构已设计好** — ideal_buy / secondary_buy / stop_loss / take_profit 四个字段已经在 schema 和 Agent 输出中。
4. **market_strategy 蓝图** — 市场环境判断(进攻/均衡/防守)的框架已有，可以直接用于风控模式映射。

**最大的缺口不在基础设施，而在"策略→信号→回测→置信度"这条数据闭环。**

---

## 六、前端 UI 调整方案

> 设计原则：与现有终端风格保持一致（深色背景 + glass Card + 青色主色调 + 动画 gauge），新增组件复用已有设计系统（`Card`, `Badge`, `ScoreGauge`, `MetricRow`, `Pagination`）。

### 6.1 导航栏调整

**当前**：4 个 Dock 图标（首页 / 问股 / 回测 / 设置）

**调整**：新增 1 个顶级页面 —— **信号看板**

```
DockNav 图标顺序（共 5 个）：
┌──────────────────────────────┐
│ 📊 Logo                      │
│ 🏠 首页 (/)                   │
│ 💬 问股 (/chat)               │
│ 🎯 信号 (/signals)  ← [NEW]  │
│ 📋 回测 (/backtest)           │
│ ⚙️ 设置 (/settings)           │
│ 🚪 退出                      │
└──────────────────────────────┘
```

信号图标附带红点 Badge（同问股的 `completionBadge` 模式），当有新信号触发时闪烁。

---

### 6.2 首页报告区增强

报告展示流程（ReportSummary）的调整：

```
当前：                          新增：
ReportOverview                  ReportOverview（增强）
  ├─ 股票信息 Card                ├─ 股票信息 Card
  ├─ Key Insights                 ├─ Key Insights
  ├─ 操作建议 + 趋势预测          ├─ 操作建议 + 趋势预测
  └─ ScoreGauge (情绪)            ├─ ScoreGauge (情绪)
                                  └─ MultiFactorGauge [NEW] ← 综合评分
                                
ReportStrategy                  ReportStrategy（增强）
  ├─ 理想买入                     ├─ 理想买入
  ├─ 二次买入                     ├─ 二次买入
  ├─ 止损价位                     ├─ 止损价位
  └─ 止盈目标                     ├─ 止盈目标
                                  └─ PositionCard [NEW] ← 仓位建议

ReportNews                      ReportNews（不变）

ReportDetails                   ReportDetails + ConfidenceBadge [NEW]
```

#### 6.2.1 MultiFactorGauge 组件（新增）

**位置**：ReportOverview 右侧，替换或与现有 ScoreGauge 并排

**设计**：复用 `ScoreGauge` 组件架构，增加多维度分解

```
┌─────────────────────────────────────────────┐
│  Market Sentiment    │  Composite Score      │
│  ┌─────────────┐     │  ┌─────────────┐      │
│  │   ╭===╮     │     │  │   ╭===╮     │      │
│  │   │ 62 │    │     │  │   │ 78 │    │      │
│  │   ╰===╯     │     │  │   ╰===╯     │      │
│  │   乐观      │     │  │  推荐买入    │      │
│  └─────────────┘     │  └─────────────┘      │
│                      │                       │
│                      │  技术面 ████████░░ 32 │
│                      │  基本面 ██████░░░░ 22 │
│                      │  资金面 ████░░░░░░ 14 │
│                      │  市场面 ██████░░░░  8 │
│                      │  ─────────────── 76   │
└─────────────────────────────────────────────┘
```

**实现**：
- 左侧保留现有 `ScoreGauge`（情绪/贪婪恐惧指数）
- 右侧新增 `CompositeScoreGauge`（综合打分 0-100）
  - 复用 `ScoreGauge` 的 SVG 圆弧动画
  - 下方增加 4 个 `FactorBar` 进度条（技术面/基本面/资金面/市场面）
  - 颜色映射：`≥85 → #00ff88(绿)`, `≥70 → #00d4ff(青)`, `≥55 → #a855f7(紫)`, `<55 → #ff4466(红)`

**数据来源**：后端 API 在报告中返回新字段：
```typescript
// types/analysis.ts 新增
interface CompositeScore {
  total: number;         // 0-100
  technical: number;     // 0-40
  fundamental: number;   // 0-30
  moneyFlow: number;     // 0-20
  market: number;        // 0-10
  label: string;         // "强烈推荐" | "推荐买入" | ...
  confidence: number;    // 0-100，来自 SignalConfidenceEngine
}
```

#### 6.2.2 PositionCard 组件（新增）

**位置**：ReportStrategy 区域下方，与狙击点位并列

**设计**：复用 `StrategyItem` 的设计模式（圆角卡片 + 底部彩色指示条）

```
┌──────── STRATEGY POINTS 狙击点位 ────────┐
│ ┌理想买入──┐ ┌二次买入──┐ ┌止损价位──┐ ┌止盈目标──┐ │
│ │ ¥23.50  │ │ ¥22.80  │ │ ¥21.50  │ │ ¥26.80  │ │
│ └─ green ─┘ └─ cyan ──┘ └─ red ───┘ └─amber──┘ │
│                                                   │
│ ┌──────── POSITION ADVICE 仓位建议 [NEW] ────────┐│
│ │ ┌建议仓位─┐ ┌风险敞口──┐ ┌盈亏比───┐ ┌置信度──┐ ││
│ │ │  15%   │ │ ¥3,200  │ │ 1:2.5  │ │  78分  │ ││
│ │ └─ cyan ─┘ └─amber──┘ └─green──┘ └─purple─┘ ││
│ └─────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────┘
```

**数据来源**：
```typescript
// types/analysis.ts 新增
interface PositionAdvice {
  positionPct: number;      // 建议仓位百分比
  riskAmount: number;       // 风险敞口金额
  profitLossRatio: string;  // 盈亏比
  confidence: number;       // 置信度
}
```

#### 6.2.3 ConfidenceBadge 组件（新增）

**位置**：操作建议卡片中，紧跟"买入/持有/观望"文字后面

**设计**：复用 `Badge` 组件 + 微光动画

```
┌─────────────────────────────────┐
│ ✅ 操作建议                      │
│ 买入  [置信度 78] ← ConfidenceBadge │
└─────────────────────────────────┘
```

- `≥80`：Badge variant=`success` + glow
- `60-79`：Badge variant=`warning`
- `<60`：Badge variant=`default`

---

### 6.3 信号看板页面（新增 `/signals`）

**布局**：参照 BacktestPage 的"左侧统计 + 右侧列表"模式

```
┌─────────────────────────────────────────────────────────┐
│ 🎯 信号看板           [筛选: 全部 ▾] [状态: 活跃 ▾]      │
├────────────┬────────────────────────────────────────────┤
│            │                                            │
│ ┌ 绩效概览 ┐│ ┌ 活跃信号列表 ─────────────────────────────┐│
│ │胜率  62% ││ │Code │方向│入场价│止损│止盈│仓位│置信度│状态  ││
│ │盈亏比1.8 ││ │━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━││
│ │信号数 15 ││ │600519│买入│¥1850│¥1780│¥2050│15%│ 82 │活跃  ││
│ │活跃    5 ││ │002594│买入│¥28.5│¥26.8│¥33.0│10%│ 71 │已入场 ││
│ │止盈    7 ││ │00700 │观望│  —  │  —  │  —  │ 0%│ 45 │过期  ││
│ │止损    3 ││ │AAPL  │买入│$198 │$190 │$220 │12%│ 76 │止盈✓ ││
│ │          ││ │...                                       ││
│ └──────────┘│ └──────────────────────────────────────────┘│
│            │                                            │
│ ┌ 策略排行 ┐│ ┌ 月度绩效曲线 [NEW] ─────────────────────┐ │
│ │KDJ超卖 68%│ │  ▁▂▃▅▇▆▅▃▂▄▆▇▅▃                       │ │
│ │均线收敛 59%│ │  +6.2%  累计收益                        │ │
│ │缩量回踩 55%│ └ ────────────────────────────────────────┘│
│ └──────────┘│                                            │
├────────────┴────────────────────────────────────────────┤
│ ⚠️ 仅供研究参考，不构成投资建议                            │
└─────────────────────────────────────────────────────────┘
```

**组件拆分**：

| 组件 | 复用基础 | 说明 |
| --- | --- | --- |
| `SignalPerformanceSummary` | 复用 `PerformanceCard` + `MetricRow` | 左上绩效概览 |
| `StrategyRanking` | 新组件，复用 `Card` + 进度条 | 左下策略排行 |
| `ActiveSignalTable` | 复用 BacktestPage 的表格 + `Badge` + `boolIcon` | 右上信号列表 |
| `MonthlyPerfChart` | 新组件（可用 SVG 折线或 `recharts`） | 右下绩效曲线 |

**数据类型**：
```typescript
// types/signals.ts [NEW]
interface SignalItem {
  id: number;
  code: string;
  stockName: string;
  direction: 'long' | 'cash';
  strategyName: string;
  entryPrice: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  positionPct: number;
  confidence: number;
  status: 'pending' | 'active' | 'take_profit' | 'stop_loss' | 'expired';
  createdAt: string;
  closedAt: string | null;
  returnPct: number | null;
}

interface SignalSummary {
  totalSignals: number;
  activeCount: number;
  winCount: number;
  lossCount: number;
  winRate: number;
  profitLossRatio: number;
  avgReturnPct: number;
  strategyRanking: Array<{
    name: string;
    winRate: number;
    signalCount: number;
  }>;
}
```

---

### 6.4 回测页面增强

**当前 BacktestPage 已有**：PerformanceCard + 结果列表

**新增**：策略维度的回测数据展示

```
┌─ Performance Cards （现有 + 新增）─────────────┐
│                                               │
│ ┌ Overall ──────┐  ┌ By Strategy [NEW] ──────┐│
│ │Direction  62% │  │                         ││
│ │Win Rate   58% │  │ kdj_rsi_oversold    68% ││
│ │Avg Return 2.3%│  │ ma_convergence      59% ││
│ │SL Rate   18%  │  │ shrink_pullback     55% ││
│ │...            │  │ bull_trend_follow   52% ││
│ └───────────────┘  │ atr_squeeze         48% ││
│                    │ wave_theory     ⚠️ 41% ││
│ ┌ Stock: 600519 ─┐ │                         ││
│ │Direction  75% │  │ [淘汰建议: wave_theory] ││
│ │Win Rate   70% │  └─────────────────────────┘│
│ │...            │                              │
│ └───────────────┘                              │
└────────────────────────────────────────────────┘
```

**新增组件**：

- `StrategyPerformanceCard`：每个策略独立的胜率/回撤/夏普比率
- 结果表新增 `strategy` 列（信号来源策略名）

---

### 6.5 API 新增接口清单

| HTTP Method | Path | 用途 | 前端消费者 |
| --- | --- | --- | --- |
| `GET` | `/api/signals` | 信号列表（带筛选/分页） | SignalsPage |
| `GET` | `/api/signals/summary` | 信号绩效汇总 | SignalPerformanceSummary |
| `GET` | `/api/signals/:id` | 信号详情 | SignalDetail (Drawer) |
| `GET` | `/api/backtest/strategy-summary` | 按策略维度的回测汇总 | StrategyPerformanceCard |
| `PATCH` | `/api/analysis/report` | 报告新增 composite_score / position_advice | ReportOverview |

---

### 6.6 前端实施优先级

| 阶段 | 前端组件 | 依赖的后端模块 | 工作量 |
| --- | --- | --- | --- |
| **P1** | `ConfidenceBadge` （Badge 复用） | SignalConfidenceEngine | 0.5 天 |
| **P1** | `StrategyPerformanceCard` | StrategyBacktester | 1 天 |
| **P2** | `CompositeScoreGauge` + `FactorBar` | MultiFactorScorer | 1.5 天 |
| **P2** | `PositionCard`（StrategyItem 复用） | PositionSizer | 0.5 天 |
| **P3** | `SignalsPage` 整页（信号列表+绩效+排行） | SignalTracker | 3 天 |
| **P3** | `MonthlyPerfChart` 绩效曲线 | 信号历史数据 | 1 天 |

> [!NOTE]
> 所有新增组件的视觉风格严格遵循现有设计系统：深色终端风格、glass Card、cyan/emerald/amber/purple 四色体系、ScoreGauge 动画弧线、MetricRow 水平指标行、Badge 发光标签。不引入新的 UI 库。
