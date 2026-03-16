# Qlib 整合实施文档

> daily_stock_analysis × Qlib 深度整合完整实施方案

## 1. 产品愿景与最终形态

### 1.1 整合前后对比

| 维度 | 整合前（当前） | 整合后（目标） |
|------|-------------|-------------|
| **趋势预测** | 规则引擎（MA 排列 + 乖离率） | 规则引擎 **+ ML 模型预测**（LightGBM/LSTM） |
| **分析因子** | 15 个技术因子 | **158+ 个** Alpha 因子 + 15 个技术因子 |
| **信号置信度** | 规则打分 0-100 | **ML 概率** + 规则打分（双引擎融合） |
| **回测能力** | 方向准确率统计 | **专业级**（IC/ICIR/Sharpe/MaxDD/年化收益） |
| **市场适应性** | 静态规则 | **滚动重训** + 市场 regime 自适应 |
| **前端展示** | 决策仪表盘 | 增加 **ML 信号卡片 + 因子雷达图 + 专业回测报告** |

### 1.2 产品最终形态

```
┌──────────────────────────────────────────────────────┐
│                 用户看到的变化                         │
│                                                       │
│  📊 个股分析报告 新增内容:                             │
│  ┌─────────────────────────────────────────────┐     │
│  │ 🤖 AI 量化信号                               │     │
│  │ ├ ML 预测方向: 看涨 ↑  置信度: 72%           │     │
│  │ ├ 预测排名: 全市场前 15%                      │     │
│  │ ├ 因子健康度: 技术 ★★★★ / 动量 ★★★★★        │     │
│  │ └ 模型: LightGBM (Alpha158) 上次训练: 3天前  │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  📈 回测页面 增强:                                    │
│  ┌─────────────────────────────────────────────┐     │
│  │ 整体表现                                     │     │
│  │ ├ 年化超额收益: 15.2%                        │     │
│  │ ├ 信息比率 (IR): 1.45                        │     │
│  │ ├ 最大回撤: -8.3%                            │     │
│  │ └ Sharpe 比率: 1.82                          │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ⚙️ 设置页面 新增:                                   │
│  ┌─────────────────────────────────────────────┐     │
│  │ Qlib 量化引擎                                │     │
│  │ ├ 启用 ML 预测: [开关]                        │     │
│  │ ├ 预测模型: [LightGBM ▾]                     │     │
│  │ ├ 数据状态: 已同步至 2026-03-16 ✅            │     │
│  │ └ 上次模型训练: 2026-03-13 [重新训练]         │     │
│  └─────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

1. **可选模块**：所有 Qlib 功能通过 `ENABLE_QLIB=true` 开关控制，不影响现有功能
2. **优雅降级**：Qlib 不可用时自动回退到纯规则引擎，零感知
3. **渐进式交付**：分 4 个 Phase 逐步上线，每个 Phase 可独立验证和发布
4. **前后端同步**：每个 Phase 的后端 API 和前端 UI 同步规划

---

## 2. 技术架构（最终态）

```
┌─────────────────── Frontend (dsa-web) ───────────────────┐
│  HomePage    SignalsPage    BacktestPage    SettingsPage  │
│  ├ ML信号卡片  ├ 因子雷达图   ├ 专业报告     ├ Qlib配置  │
│  └ 增强仪表盘  └ ML排名      └ IC/Sharpe图  └ 模型管理  │
└──────────────────────────┬──────────────────────────────┘
                           │ REST API
┌──────────────────────────┴──────────────────────────────┐
│              Backend API (FastAPI)                        │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ /api/v1/    │ │ /api/v1/     │ │ /api/v1/qlib/    │  │
│  │ analysis/*  │ │ backtest/*   │ │ status           │  │
│  │ (增强)      │ │ (增强)       │ │ predict/{code}   │  │
│  │             │ │              │ │ factors/{code}   │  │
│  │             │ │              │ │ retrain          │  │
│  └──────┬──────┘ └──────┬───────┘ └───────┬──────────┘  │
│         │               │                  │              │
│  ┌──────┴───────────────┴──────────────────┴───────────┐ │
│  │              Service Layer                           │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │ │
│  │  │AnalysisSvc  │  │BacktestSvc   │  │QlibService │ │ │
│  │  │(修改: 注入  │  │(增强: Qlib   │  │(新增)      │ │ │
│  │  │ ML预测)     │  │ 回测引擎)    │  │            │ │ │
│  │  └──────┬──────┘  └──────┬───────┘  └──────┬─────┘ │ │
│  │         │               │                  │        │ │
│  │  ┌──────┴───────────────┴──────────────────┴──────┐ │ │
│  │  │              QlibBridge (核心桥接层)             │ │ │
│  │  │  ├ data_sync()      — 数据同步                  │ │ │
│  │  │  ├ get_factors()    — Alpha158 因子计算         │ │ │
│  │  │  ├ predict()        — ML 模型预测               │ │ │
│  │  │  ├ train_model()    — 模型训练/重训             │ │ │
│  │  │  └ run_backtest()   — Qlib 回测引擎            │ │ │
│  │  └──────────────────────┬────────────────────────┘ │ │
│  └─────────────────────────┼─────────────────────────┘  │
│                            │                             │
│  ┌─────────────────────────┴───────────────────────────┐ │
│  │                  Qlib Core                           │ │
│  │  ~/.qlib/qlib_data/cn_data/  (二进制数据存储)       │ │
│  │  data/qlib_models/            (训练好的模型)        │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 实施计划

### Phase 1：Qlib 基础集成 + 因子扩展（1-2 周）

**目标**：安装 Qlib、同步 A 股数据、Alpha158 因子注入到分析链路

#### 3.1.1 后端实施

##### 新增文件

| 文件 | 职责 |
|------|------|
| `src/qlib_bridge.py` | **核心桥接层** — 封装 Qlib 的所有交互 |
| `scripts/sync_data_to_qlib.py` | 数据同步脚本（AkShare → Qlib 二进制格式） |
| `api/v1/endpoints/qlib.py` | Qlib 相关 API 端点 |
| `api/v1/schemas/qlib.py` | Qlib API 数据结构定义 |

##### `src/qlib_bridge.py` 详细设计

```python
"""Qlib 桥接层 - 封装 Qlib 的所有对外交互。

设计原则:
  - 单例模式，全局共享 Qlib 初始化状态
  - 所有方法 fail-safe，Qlib 不可用时返回 None
  - 线程安全
"""
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class MLPrediction:
    """ML 模型预测结果。"""
    code: str
    direction: str          # "up" / "down" / "neutral"
    confidence: float       # 0.0 - 1.0
    predicted_return: float # 预测收益率
    ic_rank: int           # 全市场排名分位 (0-100, 越高越好)
    model_name: str        # 使用的模型名称
    model_date: str        # 模型训练日期

@dataclass
class FactorResult:
    """Alpha 因子计算结果。"""
    code: str
    factor_values: Dict[str, float]  # 因子名 → 因子值
    factor_count: int
    factor_set: str  # "alpha158" / "alpha360"

@dataclass 
class QlibBacktestResult:
    """Qlib 专业回测结果。"""
    annualized_return: float
    information_ratio: float
    max_drawdown: float
    sharpe_ratio: float
    ic_mean: float
    icir: float
    win_rate: float  # 日胜率
    report_data: Dict[str, Any]  # 完整报告数据

class QlibBridge:
    """Qlib 桥接层。"""
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def initialize(self, data_dir: Optional[str] = None) -> bool:
        """初始化 Qlib 环境。"""
        if self._initialized:
            return True
        try:
            import qlib
            from qlib.constant import REG_CN
            uri = data_dir or os.getenv(
                "QLIB_DATA_DIR",
                str(Path.home() / ".qlib/qlib_data/cn_data")
            )
            qlib.init(provider_uri=uri, region=REG_CN)
            self._initialized = True
            logger.info(f"Qlib 初始化成功: {uri}")
            return True
        except Exception as e:
            logger.warning(f"Qlib 初始化失败（将使用纯规则引擎）: {e}")
            return False

    @property
    def is_available(self) -> bool:
        return self._initialized

    def get_alpha158_factors(
        self, code: str, start_date: str, end_date: str
    ) -> Optional[FactorResult]:
        """计算 Alpha158 因子。"""
        if not self._initialized:
            return None
        try:
            from qlib.contrib.data.handler import Alpha158
            from qlib.data import D

            # 转换代码格式: 600519 -> SH600519
            qlib_code = self._to_qlib_code(code)
            handler = Alpha158(
                instruments=[qlib_code],
                start_time=start_date,
                end_time=end_date,
            )
            df = handler.fetch()
            if df.empty:
                return None
            latest = df.iloc[-1]
            return FactorResult(
                code=code,
                factor_values=latest.to_dict(),
                factor_count=len(latest),
                factor_set="alpha158",
            )
        except Exception as e:
            logger.warning(f"Alpha158 因子计算失败 {code}: {e}")
            return None

    def predict(self, code: str) -> Optional[MLPrediction]:
        """使用预训练模型预测。"""
        if not self._initialized:
            return None
        try:
            model = self._load_model()
            if model is None:
                return None
            # 获取最新因子数据
            # ...预测逻辑...
            return MLPrediction(...)
        except Exception as e:
            logger.warning(f"ML 预测失败 {code}: {e}")
            return None

    def _to_qlib_code(self, code: str) -> str:
        """转换股票代码为 Qlib 格式。"""
        code = code.upper().replace("HK", "")
        if code.startswith("6"):
            return f"SH{code}"
        elif code.startswith(("0", "3")):
            return f"SZ{code}"
        return code

    def _load_model(self):
        """加载预训练模型。"""
        model_dir = os.getenv("QLIB_MODEL_DIR", "data/qlib_models")
        # ...加载逻辑...
```

##### 修改文件

| 文件 | 改动说明 |
|------|---------|
| `src/config.py` | 新增 Qlib 相关配置项 |
| `src/core/pipeline.py` | 注入 Qlib 因子和 ML 预测到分析流程 |
| `src/core/multi_factor_scorer.py` | 扩展评分维度，接入 Alpha158 因子 |
| `src/analyzer.py` | 增强 LLM Prompt 模板，加入 ML 预测和因子摘要 |
| `requirements.txt` | 添加 `pyqlib` 可选依赖 |
| `api/v1/router.py` | 注册 Qlib API 路由 |

##### `src/config.py` 新增配置

```python
# ============================================================
# Qlib 量化引擎配置
# ============================================================
self.enable_qlib: bool = os.getenv("ENABLE_QLIB", "false").lower() == "true"
self.qlib_data_dir: str = os.getenv(
    "QLIB_DATA_DIR", 
    str(Path.home() / ".qlib/qlib_data/cn_data")
)
self.qlib_model: str = os.getenv("QLIB_MODEL", "lightgbm")
self.qlib_model_dir: str = os.getenv("QLIB_MODEL_DIR", "data/qlib_models")
self.enable_qlib_factors: bool = os.getenv(
    "ENABLE_QLIB_FACTORS", "true"
).lower() == "true"
self.enable_ml_prediction: bool = os.getenv(
    "ENABLE_ML_PREDICTION", "true"
).lower() == "true"
```

##### `src/core/pipeline.py` 改动要点

在 `analyze_stock()` 方法中的 Step 3（趋势分析）之后，新增：

```python
# Step 3.5: Qlib ML 预测（可选模块）
ml_prediction = None
qlib_factors = None
if self.config.enable_qlib and hasattr(self, 'qlib_bridge') and self.qlib_bridge.is_available:
    # 3.5a: Alpha158 因子
    if self.config.enable_qlib_factors:
        try:
            end = date.today().isoformat()
            start = (date.today() - timedelta(days=89)).isoformat()
            qlib_factors = self.qlib_bridge.get_alpha158_factors(code, start, end)
            if qlib_factors:
                logger.info(f"{stock_name}({code}) Alpha158 因子计算完成: "
                           f"{qlib_factors.factor_count} 个因子")
        except Exception as e:
            logger.warning(f"{stock_name}({code}) Qlib 因子计算失败: {e}")

    # 3.5b: ML 预测
    if self.config.enable_ml_prediction:
        try:
            ml_prediction = self.qlib_bridge.predict(code)
            if ml_prediction:
                logger.info(f"{stock_name}({code}) ML预测: "
                           f"方向={ml_prediction.direction}, "
                           f"置信度={ml_prediction.confidence:.1%}, "
                           f"排名=前{100-ml_prediction.ic_rank}%")
        except Exception as e:
            logger.warning(f"{stock_name}({code}) ML预测失败: {e}")
```

然后在 `_enhance_context()` 中注入：

```python
# 添加 ML 预测
if ml_prediction:
    enhanced['ml_prediction'] = {
        'direction': ml_prediction.direction,
        'confidence': ml_prediction.confidence,
        'predicted_return': ml_prediction.predicted_return,
        'ic_rank': ml_prediction.ic_rank,
        'model_name': ml_prediction.model_name,
    }

# 添加 Qlib 因子摘要
if qlib_factors:
    enhanced['alpha_factors'] = {
        'factor_set': qlib_factors.factor_set,
        'factor_count': qlib_factors.factor_count,
        # 选取关键因子传给 LLM 避免 token 浪费
        'key_factors': self._select_key_factors(qlib_factors),
    }
```

##### `src/analyzer.py` Prompt 模板增强

在现有 Prompt 的「数据透视」部分后新增：

```
{%- if ml_prediction %}
## 🤖 AI 量化信号
- ML 模型预测方向: {{ml_prediction.direction}} (置信度: {{ml_prediction.confidence | percent}})
- 全市场预测排名: 前 {{100 - ml_prediction.ic_rank}}%
- 预测5日收益率: {{ml_prediction.predicted_return | percent}}
- 模型: {{ml_prediction.model_name}}

⚠️ 请将此 ML 预测作为辅助参考信号，与技术面/基本面综合判断。
{%- endif %}
```

##### 新增 API 端点 `api/v1/endpoints/qlib.py`

```python
router = APIRouter()

@router.get("/status")              # Qlib 系统状态
@router.get("/predict/{code}")      # 单股 ML 预测
@router.get("/factors/{code}")      # 单股因子数据
@router.post("/retrain")            # 触发模型重训
@router.get("/data-sync-status")    # 数据同步状态
@router.post("/data-sync")         # 手动触发数据同步
```

##### `requirements.txt` 变更

```diff
+ # Qlib 量化引擎（可选）
+ pyqlib>=0.9.0; python_version >= "3.8"
```

#### 3.1.2 前端实施

**不涉及本 Phase**。因子和 ML 预测在 Phase 1 仅注入 LLM Prompt，通过 AI 自然语言呈现在分析报告文本中。用户无感知的底层增强。

#### 3.1.3 数据同步脚本

`scripts/sync_data_to_qlib.py`：

```python
"""将 AkShare 数据转换为 Qlib 二进制格式。

Usage:
    python scripts/sync_data_to_qlib.py              # 增量同步
    python scripts/sync_data_to_qlib.py --full        # 全量同步
    python scripts/sync_data_to_qlib.py --market us  # 同步美股
"""
# 1. 从 AkShare 拉取全市场日 K 线 CSV
# 2. 转换为 Qlib 要求的 CSV 格式 (date, open, close, high, low, volume, factor)
# 3. 调用 qlib.cli.data 转换为二进制 .bin 文件
# 4. 写入 ~/.qlib/qlib_data/cn_data/
```

---

### Phase 2：ML 预测模型训练与上线（2-3 周）

**目标**：训练 LightGBM 模型（A 股全市场），集成预测结果，前端展示 ML 信号

#### 3.2.1 模型训练

新增文件 `scripts/train_qlib_model.py`：

```python
"""训练 Qlib 预测模型。

Usage:
    python scripts/train_qlib_model.py                  # 默认 LightGBM
    python scripts/train_qlib_model.py --model lstm     # 训练 LSTM
    python scripts/train_qlib_model.py --rolling         # 滚动训练
"""
# 训练配置 (workflow_config.yaml):
# - 数据集: Alpha158, CSI全市场
# - 训练集: 2015-01-01 ~ 2024-12-31
# - 验证集: 2025-01-01 ~ 2025-06-30
# - 测试集: 2025-07-01 ~ 2026-03-16
# - 标签: 5日收益率 Ref($close, -5) / $close - 1
```

训练产出物存储路径：`data/qlib_models/<model_name>_<date>/`

#### 3.2.2 后端增强

修改 `QlibBridge.predict()` 实现完整预测逻辑：
1. 加载最新训练模型
2. 获取当日 Alpha158 因子
3. 输出预测结果，计算置信度和全市场排名

新增 `src/services/qlib_service.py`：
```python
class QlibService:
    """Qlib 业务服务层。"""
    def get_prediction(self, code: str) -> Optional[MLPrediction]: ...
    def get_factors(self, code: str) -> Optional[FactorResult]: ...
    def get_status(self) -> Dict[str, Any]: ...
    def trigger_retrain(self) -> Dict[str, Any]: ...
    def get_model_performance(self) -> Dict[str, Any]: ...
```

#### 3.2.3 前端实施

##### 个股分析报告增强 (`HomePage.tsx` / 历史详情抽屉)

新增 **ML 信号卡片**组件 `components/analysis/MLSignalCard.tsx`：

```
┌─────────────────────────────────────────────┐
│ 🤖 AI 量化信号                    LightGBM  │
│                                              │
│  预测方向    置信度    全市场排名             │
│  ↑ 看涨     72%      前 15%                 │
│                                              │
│  ├ 5日预测收益: +2.3%                        │
│  ├ 动量因子: 强 ████████░░                   │
│  ├ 波动率因子: 中 █████░░░░░                 │
│  └ 流动性因子: 强 ████████░░                 │
│                                              │
│  模型训练于 2026-03-13 | 更新于 5 分钟前      │
└─────────────────────────────────────────────┘
```

##### `SettingsPage.tsx` 新增 Qlib 配置区域

```
┌─────────────────────────────────────────────┐
│ Qlib 量化引擎                                │
│                                              │
│  启用 ML 预测          [━━━━━ ON]            │
│  预测模型              [LightGBM       ▾]    │
│  数据同步状态          已同步至 2026-03-16 ✅ │
│  模型训练日期          2026-03-13             │
│                                              │
│  [手动同步数据]  [重新训练模型]               │
└─────────────────────────────────────────────┘
```

##### API 调用 — 新增 `apps/dsa-web/src/api/qlib.ts`

```typescript
export const qlibApi = {
  getStatus: () => api.get('/api/v1/qlib/status'),
  getPrediction: (code: string) => api.get(`/api/v1/qlib/predict/${code}`),
  getFactors: (code: string) => api.get(`/api/v1/qlib/factors/${code}`),
  triggerRetrain: () => api.post('/api/v1/qlib/retrain'),
  triggerDataSync: () => api.post('/api/v1/qlib/data-sync'),
};
```

---

### Phase 3：专业回测引擎集成（1-2 周）

**目标**：用 Qlib 回测引擎替代/增强现有简单回测，前端展示专业回测报告

#### 3.3.1 后端实施

`QlibBridge.run_backtest()` 实现：
- 将 daily_stock_analysis 的买卖信号转换为 Qlib 策略格式
- 在 Qlib 回测引擎中运行
- 输出：年化收益、IR、MaxDD、Sharpe、IC/ICIR 等指标

增强现有 `api/v1/endpoints/backtest.py`：
- 新增 `/api/v1/backtest/qlib-report` 端点：返回 Qlib 专业回测数据
- 修改 `PerformanceMetrics` Schema，新增 `sharpe_ratio`, `ic_mean`, `icir`, `annualized_excess_return`

#### 3.3.2 前端实施

增强 `BacktestPage.tsx`：

```
┌─────────────────────────────────────────────────────┐
│ 📊 回测报告                           [下载 PDF]    │
│                                                      │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  │
│  │年化   │  │Sharpe│  │MaxDD │  │IR    │  │胜率   │  │
│  │15.2% │  │1.82  │  │-8.3% │  │1.45  │  │58.3% │  │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  │
│                                                      │
│  📈 累计收益曲线                                     │
│  [Chart: 策略收益 vs 基准收益]                        │
│                                                      │
│  📊 月度 IC 热力图                                    │
│  [Heatmap: 12个月 × 年]                              │
│                                                      │
│  数据来源: Qlib 回测引擎 | 含交易成本 (双边 0.3%)     │
└─────────────────────────────────────────────────────┘
```

新增前端组件：
- `components/backtest/QlibReportCard.tsx`：指标卡片
- `components/backtest/CumulativeReturnChart.tsx`：累计收益曲线（使用 recharts）
- `components/backtest/ICHeatmap.tsx`：IC 热力图

---

### Phase 4：模型滚动训练 + 市场适应（1-2 周）

**目标**：自动定期重训模型，根据市场 regime 调整策略参数

#### 3.4.1 自动滚动训练

新增 `src/jobs/qlib_retrain_job.py`：

```python
"""Qlib 模型自动滚动训练任务。

配置:
  QLIB_AUTO_RETRAIN=true
  QLIB_RETRAIN_INTERVAL_DAYS=30    # 每30天重训
  QLIB_RETRAIN_SCHEDULE="02:00"    # 凌晨2点执行
"""
```

整合到现有调度器 `src/scheduler.py`，添加模型重训定时任务。

#### 3.4.2 前端状态展示

`SettingsPage.tsx` 中新增模型训练状态和历史：

```
┌─────────────────────────────────────────────┐
│ 模型训练历史                                  │
│                                              │
│  2026-03-13  LightGBM  IC: 0.052  ✅ 成功   │
│  2026-02-11  LightGBM  IC: 0.048  ✅ 成功   │
│  2026-01-12  LightGBM  IC: 0.055  ✅ 成功   │
│                                              │
│  下次自动训练: 2026-04-12 02:00              │
└─────────────────────────────────────────────┘
```

---

## 4. 资源依赖

### 4.1 Python 依赖

```
pyqlib>=0.9.0              # Qlib 核心（含 LightGBM）
numpy>=1.20.0              # 数值计算（已有）
pandas>=1.3.0              # 数据处理（已有）
torch>=1.8.0               # PyTorch（Phase 4 可选，LSTM/Transformer 模型需要）
```

安装方式（可选安装）：
```bash
pip install pyqlib            # 基础安装
pip install pyqlib[analysis]  # 含 Jupyter 分析支持
```

### 4.2 数据资源

| 资源 | 大小 | 说明 |
|------|------|------|
| A 股日 K 数据（Qlib 格式） | ~2GB | 从 AkShare 转换或社区下载 |
| 训练好的 LightGBM 模型 | ~50MB | 首次需训练，后续增量 |
| 磁盘空间 | ≥5GB | 数据 + 模型 + 临时文件 |

### 4.3 计算资源

| Phase | CPU | 内存 | GPU | 时间 |
|-------|-----|------|-----|------|
| 数据同步 | 1 核 | 2GB | 不需要 | ~30 分钟 |
| LightGBM 训练 | 4 核 | 8GB | 不需要 | ~20 分钟 |
| LSTM 训练（可选） | 4 核 | 16GB | 推荐 | ~2 小时 |

### 4.4 外部服务

| 服务 | 用途 | 必须？ |
|------|------|--------|
| AkShare | A 股数据源（数据同步用） | 是（已有） |
| LLM API | AI 分析（现有） | 是（已有） |
| Cron/定时器 | 数据同步、模型重训 | 建议 |

---

## 5. 环境变量汇总

```env
# ============================================================
# Qlib 量化引擎配置（所有配置可选，default: 关闭）
# ============================================================

# 核心开关
ENABLE_QLIB=false                                     # 主开关
ENABLE_QLIB_FACTORS=true                              # Alpha158 因子
ENABLE_ML_PREDICTION=true                              # ML 预测

# 数据配置
QLIB_DATA_DIR=~/.qlib/qlib_data/cn_data               # 数据目录
QLIB_DATA_SYNC_SCHEDULE=18:30                          # 数据同步时间

# 模型配置
QLIB_MODEL=lightgbm                                    # 模型类型
QLIB_MODEL_DIR=data/qlib_models                        # 模型存储目录

# 滚动训练（Phase 4）
QLIB_AUTO_RETRAIN=false                                # 自动重训
QLIB_RETRAIN_INTERVAL_DAYS=30                          # 重训间隔
QLIB_RETRAIN_SCHEDULE=02:00                            # 重训时间
```

---

## 6. 文件清单（完整变更列表）

### 新增文件

| 文件 | Phase | 说明 |
|------|-------|------|
| `src/qlib_bridge.py` | 1 | 核心桥接层 |
| `src/services/qlib_service.py` | 2 | Qlib 业务服务 |
| `api/v1/endpoints/qlib.py` | 1 | Qlib API 端点 |
| `api/v1/schemas/qlib.py` | 1 | Qlib API Schema |
| `scripts/sync_data_to_qlib.py` | 1 | 数据同步脚本 |
| `scripts/train_qlib_model.py` | 2 | 模型训练脚本 |
| `src/jobs/qlib_retrain_job.py` | 4 | 自动重训任务 |
| `apps/dsa-web/src/api/qlib.ts` | 2 | 前端 Qlib API |
| `apps/dsa-web/src/components/analysis/MLSignalCard.tsx` | 2 | ML信号卡片 |
| `apps/dsa-web/src/components/backtest/QlibReportCard.tsx` | 3 | 回测指标卡片 |
| `apps/dsa-web/src/components/backtest/CumulativeReturnChart.tsx` | 3 | 收益曲线图 |
| `tests/test_qlib_bridge.py` | 1 | 桥接层单元测试 |
| `tests/test_qlib_service.py` | 2 | 服务层单元测试 |
| `tests/test_qlib_api.py` | 2 | API 端点测试 |

### 修改文件

| 文件 | Phase | 改动说明 |
|------|-------|---------|
| `src/config.py` | 1 | 新增 Qlib 配置项（约 15 行） |
| `src/core/pipeline.py` | 1 | 注入 Qlib 因子/预测（约 40 行） |
| `src/core/multi_factor_scorer.py` | 1 | 扩展评分维度（约 50 行） |
| `src/analyzer.py` | 1 | Prompt 增强（约 20 行） |
| `requirements.txt` | 1 | 新增 pyqlib 依赖 |
| `.env.example` | 1 | 新增 Qlib 配置说明 |
| `api/v1/router.py` | 1 | 注册 Qlib 路由 |
| `api/v1/endpoints/backtest.py` | 3 | 增强回测 API |
| `api/v1/schemas/backtest.py` | 3 | 扩展回测 Schema |
| `apps/dsa-web/src/pages/BacktestPage.tsx` | 3 | 增强回测页面 |
| `apps/dsa-web/src/pages/SettingsPage.tsx` | 2 | 新增 Qlib 配置区域 |
| `apps/dsa-web/src/pages/HomePage.tsx` | 2 | 集成 ML 信号卡片 |
| `test.sh` | 1 | 新增 Qlib 测试场景 |

---

## 7. 里程碑与交付时间

| 里程碑 | 内容 | 交付物 | 预计时间 |
|--------|------|--------|---------|
| **M1** | Qlib 安装 + 数据同步成功 | 数据同步脚本 + 验证报告 | 第 1 周 |
| **M2** | Alpha158 因子注入 Pipeline | 增强分析报告（含因子） | 第 2 周 |
| **M3** | LightGBM 模型训练 + 预测 API | ML 预测 API + 单元测试 | 第 3-4 周 |
| **M4** | 前端 ML 信号卡片 + 设置页 | Web UI 更新 | 第 4-5 周 |
| **M5** | Qlib 回测引擎集成 | 专业回测页面 | 第 6-7 周 |
| **M6** | 滚动训练 + 市场适应 | 自动化训练管线 | 第 8 周 |
