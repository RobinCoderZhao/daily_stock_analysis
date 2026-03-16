# Qlib 整合测试验证文档

> daily_stock_analysis × Qlib 整合完成后的完整测试验证方案

## 1. 测试策略总览

### 1.1 测试层次

```
┌───────────────────────────────────────────┐
│ Layer 4: E2E 端到端验证                    │
│  完整分析流程 + 前端展示                    │
├───────────────────────────────────────────┤
│ Layer 3: 集成测试                          │
│  Pipeline + Qlib + LLM 联合测试            │
├───────────────────────────────────────────┤
│ Layer 2: API 接口测试                      │
│  Qlib 端点 + 增强版 Backtest 端点           │
├───────────────────────────────────────────┤
│ Layer 1: 单元测试                          │
│  QlibBridge / QlibService / MultiFactorScorer │
└───────────────────────────────────────────┘
```

### 1.2 测试阶段对应关系

| 实施 Phase | 测试范围 | 通过标准 |
|-----------|---------|---------|
| Phase 1 | Qlib 安装 + 数据同步 + 因子计算 | 因子准确，降级不影响现有功能 |
| Phase 2 | ML 预测 + 前端 ML 卡片 | 预测可用，API 正确，UI 展示正常 |
| Phase 3 | 专业回测引擎 | 回测指标准确，前端图表正常 |
| Phase 4 | 滚动训练 + 自动化 | 自动训练成功，模型自动切换 |

---

## 2. Phase 1 测试：基础集成 + 因子扩展

### 2.1 Qlib 安装与初始化

#### T1.1 Qlib 安装验证

```bash
# 安装 Qlib
pip install pyqlib

# 验证安装
python3 -c "import qlib; print(f'Qlib version: {qlib.__version__}')"
```

**通过标准**：无 import 错误，版本号正确输出

#### T1.2 Qlib 初始化验证

```python
# tests/test_qlib_bridge.py::test_qlib_init
def test_qlib_init():
    """验证 Qlib 能正确初始化。"""
    bridge = QlibBridge()
    result = bridge.initialize()
    assert result is True
    assert bridge.is_available is True
```

**通过标准**：初始化成功，`is_available` 返回 `True`

#### T1.3 Qlib 初始化失败降级

```python
def test_qlib_init_failure_graceful():
    """验证 Qlib 初始化失败时优雅降级。"""
    bridge = QlibBridge()
    result = bridge.initialize(data_dir="/nonexistent/path")
    assert result is False
    assert bridge.is_available is False
    
    # 所有方法应返回 None 而不是抛异常
    assert bridge.predict("600519") is None
    assert bridge.get_alpha158_factors("600519", "2025-01-01", "2025-03-01") is None
```

**通过标准**：初始化失败时不抛异常，方法返回 None

### 2.2 数据同步

#### T1.4 数据同步脚本

```bash
# 运行同步（增量）
python scripts/sync_data_to_qlib.py

# 验证数据目录
ls -la ~/.qlib/qlib_data/cn_data/instruments/
ls -la ~/.qlib/qlib_data/cn_data/features/
```

**通过标准**：
- `instruments/` 目录有 `all.txt`、`csi300.txt` 等市场文件
- `features/` 目录有各股票代码子目录
- 每个股票目录下有 `close.bin`、`open.bin`、`high.bin`、`low.bin`、`volume.bin` 等

#### T1.5 数据完整性校验

```python
def test_data_completeness():
    """验证 Qlib 数据的完整性。"""
    import qlib
    from qlib.data import D
    
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")
    
    # 验证常见股票数据可获取
    test_stocks = ["SH600519", "SZ000001", "SH601318"]
    for stock in test_stocks:
        df = D.features([stock], ["$close", "$volume"], 
                       start_time="2025-01-01", end_time="2025-03-01")
        assert not df.empty, f"{stock} 数据为空"
        assert df["$close"].notna().any(), f"{stock} close 数据全为 NaN"
```

**通过标准**：至少 3 支常见 A 股数据可获取且非空

### 2.3 Alpha158 因子计算

#### T1.6 因子计算正确性

```python
def test_alpha158_factors():
    """验证 Alpha158 因子计算。"""
    bridge = QlibBridge()
    bridge.initialize()
    
    result = bridge.get_alpha158_factors("600519", "2025-01-01", "2025-03-01")
    assert result is not None
    assert result.factor_count >= 100  # Alpha158 应有 100+ 因子
    assert result.factor_set == "alpha158"
    
    # 验证关键因子存在
    key_factors = ["KMID", "KLEN", "KMID2", "KLOW", "KSFT"]
    for factor in key_factors:
        assert factor in result.factor_values or any(
            factor in k for k in result.factor_values
        ), f"缺少关键因子: {factor}"
```

**通过标准**：因子数量 ≥ 100，关键因子值非 NaN

#### T1.7 因子注入 Pipeline

```python
def test_pipeline_with_qlib_factors(monkeypatch):
    """验证因子正确注入到分析 Pipeline。"""
    monkeypatch.setenv("ENABLE_QLIB", "true")
    monkeypatch.setenv("ENABLE_QLIB_FACTORS", "true")
    
    pipeline = StockAnalysisPipeline()
    # Mock LLM 调用
    # ...
    result = pipeline.analyze_stock("600519", ReportType.NORMAL, "test-001")
    
    assert result is not None
    assert result.success is True
```

**通过标准**：分析结果成功，且日志中有 "Alpha158 因子计算完成" 记录

### 2.4 降级验证（核心）

#### T1.8 Qlib 关闭时不影响现有功能

```bash
# 确保 Qlib 关闭时完整流程正常
ENABLE_QLIB=false python3 main.py --stocks 600519 --no-market-review --no-notify
```

**通过标准**：
- 分析正常完成，无报错
- 分析报告与整合前一致
- 日志中无 Qlib 相关错误

#### T1.9 Qlib 数据不可用时自动降级

```python
def test_qlib_data_missing_fallback():
    """验证数据缺失时自动降级到纯规则引擎。"""
    bridge = QlibBridge()
    # 使用空数据目录
    bridge.initialize(data_dir="/tmp/empty_qlib_data")
    
    # 因子计算应返回 None 而非崩溃
    result = bridge.get_alpha158_factors("600519", "2025-01-01", "2025-03-01")
    assert result is None
```

**通过标准**：无异常，返回 None，Pipeline 继续使用规则引擎

#### T1.10 现有单元测试全量回归

```bash
# 运行全部 54 个现有单元测试
python3 -m pytest tests/ -v --tb=short

# 预期输出: ✅ 所有 54 个测试 PASSED
```

**通过标准**：所有 54 个现有测试全部通过，零失败

---

## 3. Phase 2 测试：ML 预测模型

### 3.1 模型训练验证

#### T2.1 LightGBM 模型训练

```bash
python scripts/train_qlib_model.py --model lightgbm

# 验证模型文件生成
ls -la data/qlib_models/lightgbm_*/
```

**通过标准**：
- 训练脚本无错退出
- 模型文件生成在 `data/qlib_models/` 目录
- 训练日志输出 IC、ICIR 等指标

#### T2.2 模型质量验证

```python
def test_model_quality():
    """验证模型预测质量达标。"""
    # 在测试集上评估
    metrics = evaluate_model("data/qlib_models/lightgbm_latest/")
    
    # 最低质量标准
    assert metrics["ic_mean"] > 0.02, f"IC 过低: {metrics['ic_mean']}"
    assert metrics["icir"] > 0.5, f"ICIR 过低: {metrics['icir']}"
    assert metrics["annualized_return"] > 0, "年化收益为负"
```

**通过标准**：IC > 0.02, ICIR > 0.5, 年化收益 > 0

### 3.2 预测 API 验证

#### T2.3 预测端点正确性

```bash
# 启动服务
python main.py --serve-only &

# 调用预测 API
curl -s http://localhost:9999/api/v1/qlib/predict/600519 | python3 -m json.tool
```

**预期返回**：
```json
{
  "code": "600519",
  "direction": "up",
  "confidence": 0.72,
  "predicted_return": 0.023,
  "ic_rank": 85,
  "model_name": "lightgbm",
  "model_date": "2026-03-13"
}
```

**通过标准**：
- HTTP 200
- `direction` ∈ ["up", "down", "neutral"]
- `confidence` ∈ [0, 1]
- `ic_rank` ∈ [0, 100]

#### T2.4 Qlib 状态端点

```bash
curl -s http://localhost:9999/api/v1/qlib/status | python3 -m json.tool
```

**预期返回**：
```json
{
  "enabled": true,
  "initialized": true,
  "data_dir": "~/.qlib/qlib_data/cn_data",
  "model_name": "lightgbm",
  "model_date": "2026-03-13",
  "data_last_sync": "2026-03-16",
  "factors_available": true,
  "prediction_available": true
}
```

#### T2.5 预测结果注入 LLM 分析

```bash
ENABLE_QLIB=true ENABLE_ML_PREDICTION=true \
  python3 main.py --stocks 600519 --no-market-review --no-notify 2>&1 | \
  grep -E "(ML预测|AI 量化信号)"
```

**通过标准**：日志输出 "ML预测: 方向=up, 置信度=XX%" 类信息

### 3.3 前端 UI 验证

#### T2.6 ML 信号卡片展示

1. 启动前后端：
```bash
python main.py --serve-only &
cd apps/dsa-web && npm run dev
```

2. 打开 `http://localhost:5173`
3. 分析一支 A 股（如 600519）
4. 查看分析结果页面

**通过标准**：
- 分析报告中显示 "AI 量化信号" 卡片
- 卡片内容包含：预测方向、置信度、全市场排名
- Qlib 关闭时卡片不显示（无残留 UI 元素）

#### T2.7 设置页面 Qlib 配置

1. 导航到 Settings 页面
2. 查看 "Qlib 量化引擎" 配置区域

**通过标准**：
- 显示 Qlib 启用开关
- 显示数据同步状态
- 显示模型信息
- 开关切换后立即生效

---

## 4. Phase 3 测试：专业回测引擎

### 4.1 回测引擎验证

#### T3.1 Qlib 回测执行

```python
def test_qlib_backtest():
    """验证 Qlib 回测引擎运行正确。"""
    bridge = QlibBridge()
    bridge.initialize()
    
    result = bridge.run_backtest(
        signals=test_signals,  # 历史买卖信号
        start_date="2025-01-01",
        end_date="2025-12-31",
        benchmark="SH000300",  # 沪深300基准
    )
    
    assert result is not None
    assert isinstance(result.annualized_return, float)
    assert isinstance(result.max_drawdown, float)
    assert result.max_drawdown <= 0  # 回撤应为负值
    assert isinstance(result.sharpe_ratio, float)
    assert isinstance(result.information_ratio, float)
```

**通过标准**：所有回测指标有效且类型正确

#### T3.2 回测 API 增强验证

```bash
# 获取 Qlib 回测报告
curl -s http://localhost:9999/api/v1/backtest/qlib-report | python3 -m json.tool
```

**预期返回包含**：
```json
{
  "annualized_return": 0.152,
  "sharpe_ratio": 1.82,
  "max_drawdown": -0.083,
  "information_ratio": 1.45,
  "ic_mean": 0.052,
  "icir": 1.3,
  "win_rate": 0.583,
  "cumulative_returns": [...],
  "monthly_ic": [...]
}
```

#### T3.3 现有回测 API 兼容性

```bash
# 确保现有回测 API 仍然正常
curl -s http://localhost:9999/api/v1/backtest/performance | python3 -m json.tool
curl -s http://localhost:9999/api/v1/backtest/results?page=1&limit=10 | python3 -m json.tool
```

**通过标准**：返回结构与整合前一致，字段保持向后兼容

### 4.2 前端回测页面

#### T3.4 回测页面增强验证

1. 导航到 Backtest 页面
2. 查看增强后的回测指标

**通过标准**：
- 显示年化收益、Sharpe、MaxDD、IR、胜率指标卡片
- 累计收益曲线图正常渲染（策略 vs 基准）
- 数据加载状态正确（loading → loaded）
- Qlib 关闭时回退到现有简单回测展示

---

## 5. Phase 4 测试：滚动训练 + 自动化

#### T4.1 自动重训触发

```python
def test_auto_retrain():
    """验证自动重训任务正常执行。"""
    # 模拟到达重训周期
    job = QlibRetrainJob()
    result = job.execute()
    
    assert result["status"] == "success"
    assert "model_path" in result
    assert result["metrics"]["ic_mean"] > 0
```

#### T4.2 模型热切换

```python
def test_model_hot_swap():
    """验证新模型训练后自动切换。"""
    bridge = QlibBridge()
    old_model_date = bridge.get_model_info()["model_date"]
    
    # 触发重训
    bridge.retrain()
    
    new_model_date = bridge.get_model_info()["model_date"]
    assert new_model_date > old_model_date  # 模型已更新
    
    # 验证预测使用新模型
    prediction = bridge.predict("600519")
    assert prediction.model_date == new_model_date
```

---

## 6. 回归测试清单

每个 Phase 完成后必须执行的回归测试：

### 6.1 自动化回归

```bash
# 1. 全量单元测试
python3 -m pytest tests/ -v --tb=short -q

# 2. 语法检查
./test.sh syntax

# 3. 代码识别测试
./test.sh code

# 4. YFinance 转换测试
./test.sh yfinance
```

### 6.2 功能回归

```bash
# 5. Dry-Run（数据获取）
./test.sh dry-run

# 6. A 股分析（功能核心路径）
ENABLE_QLIB=false ./test.sh a-stock --no-notify

# 7. 美股分析
ENABLE_QLIB=false ./test.sh us-stock --no-notify

# 8. Qlib 开启模式 A 股分析
ENABLE_QLIB=true ./test.sh a-stock --no-notify
```

### 6.3 前端回归

| 检查项 | 步骤 |
|--------|------|
| 首页加载 | 访问 `/`，页面正常渲染 |
| 分析触发 | 输入股票代码，触发分析，结果返回 |
| 回测页面 | 访问 BacktestPage，数据加载正常 |
| 信号页面 | 访问 SignalsPage，历史信号展示正常 |
| 设置页面 | 访问 SettingsPage，配置保存正常 |
| 自选股页面 | WatchlistPage 正常展示 |

---

## 7. 性能验证

### 7.1 分析延迟对比

| 场景 | 整合前 | 整合后（预期） | 增量（可接受范围） |
|------|--------|-------------|-------------------|
| 单股分析（Qlib 关闭） | ~5s | ~5s | +0s |
| 单股分析（Qlib 开启） | - | ~7s | +2s (**≤ 3s**) |
| 批量分析 10 支 | ~50s | ~65s | +15s (**≤ 20s**) |

```bash
# 性能对比测试
time ENABLE_QLIB=false python3 main.py --stocks 600519 --no-market-review --no-notify
time ENABLE_QLIB=true python3 main.py --stocks 600519 --no-market-review --no-notify
```

**通过标准**：Qlib 开启后单股分析增加延迟 ≤ 3 秒

### 7.2 内存占用

```bash
# 监控内存
python3 -c "
import tracemalloc
tracemalloc.start()
from src.qlib_bridge import QlibBridge
bridge = QlibBridge()
bridge.initialize()
current, peak = tracemalloc.get_traced_memory()
print(f'Qlib 初始化内存: {peak/1024/1024:.1f} MB')
"
```

**通过标准**：Qlib 初始化额外内存 ≤ 500MB

---

## 8. 验收标准总结

### 8.1 必须通过（P0）

| # | 验收项 | 验证方法 |
|---|--------|---------|
| 1 | **现有全部 54 个单元测试通过** | `pytest tests/ -v` |
| 2 | **Qlib 关闭时功能完全不受影响** | `ENABLE_QLIB=false ./test.sh all` |
| 3 | **Qlib 初始化失败时优雅降级** | T1.3 |
| 4 | **Alpha158 因子计算正确** | T1.6 |
| 5 | **ML 预测 API 返回正确格式** | T2.3 |
| 6 | **分析延迟增加 ≤ 3s** | 7.1 性能测试 |

### 8.2 应该通过（P1）

| # | 验收项 | 验证方法 |
|---|--------|---------|
| 7 | 模型 IC > 0.02 | T2.2 |
| 8 | 前端 ML 信号卡片正确展示 | T2.6 |
| 9 | 回测指标正确且完整 | T3.1 |
| 10 | 设置页面 Qlib 配置正常 | T2.7 |

### 8.3 可以后续优化（P2）

| # | 验收项 | 验证方法 |
|---|--------|---------|
| 11 | 滚动训练自动执行 | T4.1 |
| 12 | 模型热切换无中断 | T4.2 |
| 13 | 回测收益曲线图渲染正确 | T3.4 |

---

## 9. 测试脚本扩展

在现有 `test.sh` 中新增 Qlib 测试场景：

```bash
# 测试14: Qlib 基础验证
test_qlib_basic() {
    header "测试场景: Qlib 基础验证"
    info "验证 Qlib 安装和初始化..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

# 1. 导入验证
try:
    from src.qlib_bridge import QlibBridge
    print("✅ QlibBridge 导入成功")
except ImportError as e:
    print(f"❌ QlibBridge 导入失败: {e}")
    sys.exit(1)

# 2. 可选：Qlib 初始化
try:
    bridge = QlibBridge()
    if bridge.initialize():
        print("✅ Qlib 初始化成功")
        
        # 3. 因子测试
        result = bridge.get_alpha158_factors("600519", "2025-01-01", "2025-03-01")
        if result and result.factor_count > 0:
            print(f"✅ Alpha158 因子: {result.factor_count} 个")
        else:
            print("⚠️  Alpha158 因子获取失败（可能数据未同步）")
    else:
        print("⚠️  Qlib 初始化失败（可能未安装或数据未同步，正常降级）")
except Exception as e:
    print(f"⚠️  Qlib 测试异常: {e}")

# 4. 降级验证
bridge2 = QlibBridge.__new__(QlibBridge)
bridge2._initialized = False
assert bridge2.predict("600519") is None, "降级失败"
print("✅ 降级验证通过")

print("\n✅ Qlib 基础验证完成")
PYTEST

    success "Qlib 基础验证完成"
}

# 测试15: Qlib 集成分析验证
test_qlib_analysis() {
    header "测试场景: Qlib 集成分析"
    info "使用 Qlib 增强模式分析股票..."
    ENABLE_QLIB=true python3 main.py --stocks 600519 --no-market-review --no-notify
    success "Qlib 集成分析测试完成"
}
```

在 `test.sh` 的 `case` 语句中新增对应入口：
```bash
qlib|qlib-basic)
    shift
    test_qlib_basic "$@"
    ;;
qlib-analysis)
    shift
    test_qlib_analysis "$@"
    ;;
```
