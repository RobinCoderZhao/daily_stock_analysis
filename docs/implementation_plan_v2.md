# 数据与策略改进 — 详细开发实施文档 V2

> 基于 `docs/data_strategy_research.md` 研究报告  
> 日期：2026-03-14 | 分支：Dev

---

## 目录

1. [数据层修复（必做）](#一数据层修复必做)
2. [数据质量提升建议（付费接口）](#二数据质量提升建议付费接口)
3. [新增策略](#三新增策略)
4. [策略治理](#四策略治理)
5. [验证方案](#五验证方案)

---

## 一、数据层修复（必做）

### 1.1 pct_chg 口径统一

> **问题**：efinance 返回百分比（5.23），baostock 返回小数（0.0523），混用导致策略阈值判断错误。

#### [MODIFY] [base.py](file:///Users/robin/myworkdir/daily_stock_analysis/data_provider/base.py)

**修改位置**：`_clean_data()` 方法（约 L339-367）

**修改内容**：在数值类型转换后、`dropna` 之前，添加口径统一逻辑：

```python
# Normalize pct_chg to percentage format (5.23 means +5.23%)
# Some sources (baostock) return decimal format (0.0523)
if 'pct_chg' in df.columns:
    pct_series = df['pct_chg'].dropna()
    if len(pct_series) > 0:
        # Heuristic: if 95th percentile of absolute values < 1,
        # it's likely decimal format
        p95 = pct_series.abs().quantile(0.95)
        if p95 < 1.0:
            df['pct_chg'] = df['pct_chg'] * 100
            logger.debug("pct_chg normalized: decimal -> percentage format")
```

**估算**：15 行新增代码

---

### 1.2 turnover_rate 回填

> **问题**：仅 efinance/akshare 在日线数据中包含换手率。pytdx/baostock 降级时，换手率全部为 None。

#### [MODIFY] [base.py](file:///Users/robin/myworkdir/daily_stock_analysis/data_provider/base.py)

**修改位置**：`_clean_data()` 方法末尾，添加回填逻辑

**修改内容**：

```python
# Backfill turnover_rate if missing
# Formula: turnover_rate = volume / circ_shares * 100
# circ_shares can be obtained from realtime quote's circ_mv / price
if 'turnover_rate' not in df.columns or df['turnover_rate'].isna().all():
    df['turnover_rate'] = None  # placeholder, filled at manager level
    logger.debug("turnover_rate column missing from raw data, marked for backfill")
```

#### [MODIFY] [base.py](file:///Users/robin/myworkdir/daily_stock_analysis/data_provider/base.py) — DataFetcherManager

**修改位置**：`get_daily_data()` 方法，在返回 `(df, fetcher.name)` 之前

**修改内容**：在 manager 层检测并回填 turnover_rate：

```python
# Backfill turnover_rate if the winning fetcher didn't provide it
if 'turnover_rate' not in df.columns or df['turnover_rate'].isna().all():
    df = self._backfill_turnover_rate(df, stock_code)
```

新增方法 `_backfill_turnover_rate()`:

```python
def _backfill_turnover_rate(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Estimate turnover_rate from volume and circulating market cap."""
    try:
        quote = self.get_realtime_quote(stock_code)
        if quote and quote.circ_mv and quote.price and quote.price > 0:
            circ_shares = quote.circ_mv / quote.price
            if circ_shares > 0:
                df['turnover_rate'] = df['volume'] / circ_shares * 100
                df['turnover_rate'] = df['turnover_rate'].round(4)
                logger.info(f"[回填] {stock_code} turnover_rate estimated from circ_mv")
    except Exception as e:
        logger.warning(f"[回填] {stock_code} turnover_rate backfill failed: {e}")
    return df
```

**估算**：30 行新增代码

---

### 1.3 efinance 请求限流优化

> **问题**：批量分析时 efinance 高频请求导致 ServerDisconnectedError，触发连锁熔断。

#### [MODIFY] [efinance_fetcher.py](file:///Users/robin/myworkdir/daily_stock_analysis/data_provider/efinance_fetcher.py)

**修改位置**：`_enforce_rate_limit()` 方法（约 L270-289）

**修改内容**：添加最小请求间隔 + 批量模式检测：

```python
# Minimum interval between efinance requests (anti-ban)
_MIN_REQUEST_INTERVAL_MS = int(os.getenv("EFINANCE_MIN_INTERVAL_MS", "500"))

def _enforce_rate_limit(self) -> None:
    if self._last_request_time is not None:
        elapsed_ms = (time.time() - self._last_request_time) * 1000
        min_interval = max(self._MIN_REQUEST_INTERVAL_MS, self.sleep_min * 1000)
        if elapsed_ms < min_interval:
            wait_s = (min_interval - elapsed_ms) / 1000
            logger.debug(f"Rate limit: waiting {wait_s:.2f}s (min_interval={min_interval}ms)")
            time.sleep(wait_s)
    
    self.random_sleep(self.sleep_min, self.sleep_max)
    self._last_request_time = time.time()
```

**新增环境变量**：`EFINANCE_MIN_INTERVAL_MS`（默认 500ms）

**估算**：15 行修改

---

### 1.4 KDJ 指标计算

> **为新策略 "KDJ + RSI 超卖共振" 做数据准备**

#### [MODIFY] [stock_analyzer.py](file:///Users/robin/myworkdir/daily_stock_analysis/src/stock_analyzer.py)

**修改位置**：`TrendAnalysisResult` dataclass + `StockTrendAnalyzer`

**修改内容**：

1. 在 `TrendAnalysisResult` 新增字段：
   - `kdj_k: Optional[float] = None`
   - `kdj_d: Optional[float] = None`
   - `kdj_j: Optional[float] = None`
   - `kdj_signal: Optional[str] = None`（golden_cross / dead_cross / neutral）

2. 新增 `_calculate_kdj()` 方法：

```python
def _calculate_kdj(self, df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    """Calculate KDJ indicator.
    
    KDJ formula:
    RSV = (close - LLV(low, n)) / (HHV(high, n) - LLV(low, n)) * 100
    K = EMA(RSV, m1)  (or SMA)
    D = EMA(K, m2)
    J = 3*K - 2*D
    """
    low_n = df['low'].rolling(window=n, min_periods=1).min()
    high_n = df['high'].rolling(window=n, min_periods=1).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-10) * 100
    
    k = rsv.ewm(span=m1, adjust=False).mean()
    d = k.ewm(span=m2, adjust=False).mean()
    j = 3 * k - 2 * d
    
    return k.iloc[-1], d.iloc[-1], j.iloc[-1]
```

3. 在 `analyze()` 方法中调用并填充结果

**估算**：50 行新增代码

---

### 1.5 analyze_trend 工具增加 KDJ 字段输出

#### [MODIFY] [analysis_tools.py](file:///Users/robin/myworkdir/daily_stock_analysis/src/agent/tools/analysis_tools.py)

**修改内容**：在 `_handle_analyze_trend` 输出字典中添加 KDJ 字段

**估算**：10 行修改

---

## 二、数据质量提升建议（付费接口）

> 以下是购买数据接口的建议，用户可根据预算选择性实施。

### 2.1 推荐付费数据源对比

| 数据源 | 年费 | 数据范围 | 优势 | 推荐度 |
| --- | --- | --- | --- | --- |
| **Tushare Pro** | ¥500/年（5000积分） | A股全量 + 北向资金 + 基本面 | API 限流宽松，数据最全 | ⭐⭐⭐⭐⭐ |
| **聚宽 JoinQuant** | 免费/¥2000（高级） | A股全量 + 因子库 | 有回测框架，因子库强大 | ⭐⭐⭐⭐ |
| **Wind 万得** | ¥3-5万/年 | 全市场 | 机构级数据，最权威 | ⭐⭐⭐（贵） |
| **东方财富 Choice** | ¥1980/年 | A股全量 + 资金流 | 有官方 API，稳定 | ⭐⭐⭐⭐ |

### 2.2 各数据源可解决的问题

#### 🏆 Tushare Pro（最推荐，性价比最高）

配置 `TUSHARE_TOKEN` 后可解决：

| 问题 | 当前状态 | Tushare 方案 |
| --- | --- | --- |
| 换手率历史缺失 | 仅 efinance 有 | `daily_basic` 接口，全量日级换手率 |
| 北向资金中断 | 2024.08 后数据不全 | `moneyflow_hsgt` 接口，持续更新 |
| efinance 被封禁 | 高频触发限流 | Tushare 单日 500 次，限流宽松 |
| 基本面数据缺失 | 无 ROE/PE 历史 | `fina_indicator` 接口，支持 ROE/现金流 |
| 资金流向缺失 | 无主力资金数据 | `moneyflow` 接口，个股资金流 |

**建议操作（用户执行）**：
1. 访问 https://tushare.pro 注册账号
2. 获取 Token（免费 2000 积分/天，付费 5000+）
3. 在 `.env` 中设置 `TUSHARE_TOKEN=your_token_here`
4. 系统自动将 Tushare 优先级提升到 P0

#### 东方财富 Choice（如需资金流）

如果需要个股资金流向数据（策略 F 依赖），Choice 是最佳选择：
- 提供实时主力/散户资金流向
- 有板块轮动数据
- API 调用限制比爬虫宽松

**建议操作**：购买 Choice 量化接口 → 新增 `ChoiceFetcher` 数据源

### 2.3 长期数据质量路线图

```
短期（1-2 周）                     中期（1-3 月）                     长期（3-6 月）
├── 代码修复 pct_chg 口径         ├── 接入 Tushare Pro             ├── 接入 Choice 量化接口
├── turnover_rate 回填            ├── 北向资金数据恢复             ├── 自建数据清洗 pipeline
├── efinance 限流优化             ├── 基本面数据工具               ├── 数据一致性校验框架
└── KDJ 指标计算                  └── 资金流向数据工具             └── 异常数据自动告警
```

---

## 三、新增策略

### 3.1 均线粘合后发散（零工具改动）

#### [NEW] [ma_convergence_breakout.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/ma_convergence_breakout.yaml)

```yaml
name: ma_convergence_breakout
display_name: 均线粘合后发散
description: MA5/MA10/MA20三线粘合后向上发散，趋势启动信号
category: trend
confidence_weight: 0.85
applicable_market:
  - trend
  - oscillation
not_applicable_market:
  - crash
instructions: |
  ## 均线粘合后发散策略
  
  当MA5、MA10、MA20三条均线间距收窄到收盘价的1%以内（粘合），
  随后MA5向上突破MA10和MA20（发散），是趋势启动的经典信号。
  
  ### 买入条件（全部满足）：
  1. MA5、MA10、MA20最大价差 < 收盘价 × 1%
  2. MA5 > MA10 > MA20（多头排列形成）
  3. 量比 > 1.2（成交量配合放大）
  4. MA20斜率方向 = up（趋势转向）
  
  ### 卖出/回避条件：
  - MA5 跌破 MA20
  - 量比持续萎缩 < 0.8
  - 均线重新粘合但向下发散
  
  ### 风险控制：
  - 止损：跌破粘合区间最低价
  - 止盈：第一目标 = 粘合区间幅度 × 2
required_tools:
  - analyze_trend
core_rules: [1, 3]
```

---

### 3.2 ATR 收缩后突破（零工具改动）

#### [NEW] [atr_squeeze_breakout.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/atr_squeeze_breakout.yaml)

```yaml
name: atr_squeeze_breakout
display_name: ATR收缩后突破
description: ATR持续收缩后突然扩大，波动率爆发突破信号
category: trend
confidence_weight: 0.80
applicable_market:
  - trend
  - oscillation
not_applicable_market:
  - crash
instructions: |
  ## ATR收缩后突破策略
  
  当ATR(14)持续收缩表示波动率压缩（市场蓄势），
  ATR突然扩大且价格向上突破时，是趋势爆发的信号。
  
  ### 买入条件（全部满足）：
  1. atr_trend = contracting（连续5天以上ATR收缩）
  2. 当日ATR突然扩大 > 前一日ATR × 1.5
  3. 当日为阳线（收盘 > 开盘）
  4. 成交量放大（量比 > 1.5）
  
  ### 卖出/回避条件：
  - ATR再次收缩且价格未能创新高
  - 连续2日阴线
  
  ### 风险控制：
  - 止损：突破当日最低价
  - 仓位：根据ATR设定（风险金额 / ATR = 仓位数量）
required_tools:
  - analyze_trend
core_rules: [1, 2]
```

---

### 3.3 KDJ + RSI 超卖共振（需 KDJ 数据 — 1.4 节）

#### [NEW] [kdj_rsi_oversold.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/kdj_rsi_oversold.yaml)

```yaml
name: kdj_rsi_oversold
display_name: KDJ+RSI超卖共振
description: KDJ和RSI同时超卖后反弹，双指标共振买入信号
category: reversal
confidence_weight: 0.90
applicable_market:
  - trend
  - oscillation
not_applicable_market:
  - crash
instructions: |
  ## KDJ + RSI 超卖共振策略
  
  当KDJ和RSI两个独立的超卖指标同时发出超卖信号后反弹，
  形成共振买入信号。假信号率远低于单一指标。
  
  ### 买入条件（全部满足）：
  1. RSI(14) < 30（进入超卖区域）
  2. KDJ J值 < 0 或 K值 < 20
  3. KDJ出现金叉（K上穿D）
  4. 当前收盘价在MA20上方（趋势过滤器，避免下跌趋势中抄底）
  
  ### 卖出/回避条件：
  - RSI > 70（超买区域）
  - KDJ死叉（K下穿D）且J > 100
  - 跌破MA20
  
  ### 风险控制：
  - 必须在上升趋势中使用（MA20方向=up）
  - 止损：低于超卖时最低价的3%
  - 仓位：不超过总仓位30%
required_tools:
  - analyze_trend
core_rules: [2, 4]
```

---

### 3.4 高质量因子选股（需新增工具）

#### [NEW] [quality_factor.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/quality_factor.yaml)

```yaml
name: quality_factor
display_name: 高质量因子选股
description: 基于ROE/现金流/估值的高质量因子筛选，2026年最稳Alpha源
category: fundamental
confidence_weight: 0.85
applicable_market:
  - trend
  - oscillation
  - reversal
instructions: |
  ## 高质量因子选股策略（2026年验证有效）
  
  基于最新量化研究，高质量因子2026年前2月累计跑赢沪深300约2.4%。
  本策略筛选盈利稳定、现金流健康、估值合理的标的。
  
  ### 筛选条件（满足4/5即可）：
  1. 最近4季度ROE均 > 8%（盈利稳定性）
  2. 经营现金流/净利润 > 0.7（现金流质量）
  3. PE(TTM) < 行业中位数（估值不贵）
  4. 资产负债率 < 60%（财务安全）
  5. 近3年营收CAGR > 5%（可持续增长）
  
  ### 注意事项：
  - 需配合技术面策略使用（如趋势策略确认买点）
  - 仅作为选股过滤器，不提供具体买卖时点
  - 需要基本面数据工具支持
required_tools:
  - get_fundamental_profile
  - analyze_trend
core_rules: [5]
```

#### [NEW] [data_tools.py — get_fundamental_profile](file:///Users/robin/myworkdir/daily_stock_analysis/src/agent/tools/data_tools.py)

**新增工具**：`get_fundamental_profile`

**功能**：获取股票基本面数据（ROE、PE、现金流等）

**数据源优先级**：
1. Tushare Pro `fina_indicator` + `daily_basic`（如果 Token 可用）
2. Akshare `stock_financial_analysis_indicator_em`（东财免费）
3. 降级返回 `{"error": "fundamental data not available"}`

**估算**：80 行新增代码

---

### 3.5 板块轮动择时（需增强工具）

#### [NEW] [sector_rotation.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/sector_rotation.yaml)

```yaml
name: sector_rotation
display_name: 板块轮动择时
description: 基于行业板块强弱轮动的择时策略，分域建模思路
category: market
confidence_weight: 0.75
applicable_market:
  - trend
  - oscillation
instructions: |
  ## 板块轮动择时策略（2026年分域建模思路）
  
  不同板块在不同市场环境下表现差异很大。
  先判断当前强势板块，仅在强势板块内选股。
  
  ### 操作逻辑：
  1. 获取近5日行业板块涨幅排名
  2. 关注Top5强势板块中的个股
  3. 对强势板块内个股应用趋势策略
  4. 弱势板块个股给出"回避"建议
  
  ### 注意事项：
  - 板块轮动有惯性（强者恒强3-5天）
  - 但也有均值回归（连涨5天以上需警惕回调）
  - 结合大盘环境判断（牛市追强，熊市防守）
required_tools:
  - get_analysis_context
  - analyze_trend
core_rules: [1]
```

---

### 3.6 资金流向驱动（需新增工具）

#### [NEW] [fund_flow_driven.yaml](file:///Users/robin/myworkdir/daily_stock_analysis/strategies/fund_flow_driven.yaml)

```yaml
name: fund_flow_driven
display_name: 资金流向驱动
description: 主力资金持续流入+量价配合的强势延续策略
category: trend
confidence_weight: 0.70
applicable_market:
  - trend
not_applicable_market:
  - crash
instructions: |
  ## 资金流向驱动策略
  
  主力资金持续流入是股价上涨的核心驱动力。
  当量价配合良好时，强势延续概率高。
  
  ### 买入条件（全部满足）：
  1. 近5日主力资金净流入 > 0
  2. 近5日成交额持续放大
  3. 均线多头排列（MA5 > MA10 > MA20）
  4. 筹码获利盘在50%-80%（健康区间）
  
  ### 卖出/回避条件：
  - 主力资金连续3日净流出
  - 成交量突然萎缩（量比 < 0.5）
  - 获利盘 > 90%（获利盘过重，抛压大）
  
  ### 注意事项：
  - 需要资金流向数据工具支持
  - 大单流入不等于主力建仓（可能是对倒）
  - 结合筹码分布判断更可靠
required_tools:
  - get_fund_flow
  - get_chip_distribution
  - analyze_trend
core_rules: [1, 3]
```

#### [NEW] [data_tools.py — get_fund_flow](file:///Users/robin/myworkdir/daily_stock_analysis/src/agent/tools/data_tools.py)

**新增工具**：`get_fund_flow`

**功能**：获取个股资金流向数据（主力/散户/超大单/大单/中单/小单）

**数据源优先级**：
1. Akshare `stock_individual_fund_flow` (东财)
2. Tushare Pro `moneyflow`（如果 Token 可用）
3. 降级返回 error

**估算**：60 行新增代码

---

## 四、策略治理

### 4.1 移出低效策略

#### [MODIFY] [factory.py](file:///Users/robin/myworkdir/daily_stock_analysis/src/agent/factory.py)

**修改内容**：从 `DEFAULT_AGENT_SKILLS` 移除 `dragon_head` 和 `wave_theory`（如果在列表中）

---

### 4.2 注册新策略 YAML

所有新增的 6 个 YAML 文件放在 `strategies/` 目录下，系统通过 `load_skills_from_directory()` 自动加载，无需额外注册代码。

---

### 4.3 更新默认激活策略

#### [MODIFY] [factory.py](file:///Users/robin/myworkdir/daily_stock_analysis/src/agent/factory.py)

根据 confidence_weight 重新排列默认策略：

```python
DEFAULT_AGENT_SKILLS = [
    "bull_trend",              # 0.95
    "shrink_pullback",         # 0.95
    "kdj_rsi_oversold",        # 0.90 (new)
    "one_yang_three_yin",      # 0.90
    "volume_breakout",         # 0.85
    "ma_convergence_breakout", # 0.85 (new)
]
```

---

## 五、验证方案

### 5.1 语法检查

```bash
cd /Users/robin/myworkdir/daily_stock_analysis
python3 -m py_compile data_provider/base.py
python3 -m py_compile data_provider/efinance_fetcher.py
python3 -m py_compile src/stock_analyzer.py
python3 -m py_compile src/agent/tools/analysis_tools.py
python3 -m py_compile src/agent/tools/data_tools.py
python3 -m py_compile src/agent/factory.py
```

### 5.2 运行现有测试

项目已有 45 个测试文件，以下与本次改动直接相关：

```bash
# Data layer tests
python3 -m pytest tests/test_stock_code_utils.py -v
python3 -m pytest tests/test_fetcher_logging.py -v
python3 -m pytest tests/test_stock_analyzer_bias.py -v

# Agent tools tests
python3 -m pytest tests/test_agent_registry.py -v

# Pipeline integration
python3 -m pytest tests/test_pipeline_realtime_indicators.py -v
```

### 5.3 新增单元测试

#### [NEW] [test_pct_chg_normalization.py](file:///Users/robin/myworkdir/daily_stock_analysis/tests/test_pct_chg_normalization.py)

测试 pct_chg 口径统一逻辑：
- 输入小数格式 → 输出百分比格式
- 输入百分比格式 → 不变
- 混合格式 → 正确检测并转换

#### [NEW] [test_kdj_calculation.py](file:///Users/robin/myworkdir/daily_stock_analysis/tests/test_kdj_calculation.py)

测试 KDJ 计算：
- 已知数据的 K/D/J 值正确性
- 极端情况（全涨停、全跌停）
- 金叉/死叉信号判断

### 5.4 手动验证（用户在服务器上执行）

在线上服务器 `root@43.98.84.1` 上：

```bash
cd /root/export/daily_stock_analysis
git pull origin Dev

# 1. 重启服务
./ctrl.sh stop && ./ctrl.sh start

# 2. 通过 WebUI 测试
# 访问 http://devkit-suite.com/gushi
# 输入一只股票（如 600519），观察分析输出中是否包含：
#   - KDJ 指标值
#   - 换手率数据（即使 efinance 不可用时）
#   - pct_chg 值呈百分比格式

# 3. 日志检查
tail -100 logs/app.log | grep -E "pct_chg|turnover_rate|KDJ|backfill"
```

---

## 六、实施顺序与估算

| 阶段 | 内容 | 文件数 | 新增行数 | 预计耗时 |
| --- | --- | --- | --- | --- |
| **P1** | pct_chg 口径统一 | 1 | 15 | 10 min |
| **P2** | turnover_rate 回填 | 1 | 30 | 15 min |
| **P3** | efinance 限流优化 | 1 | 15 | 10 min |
| **P4** | KDJ 指标计算 + 工具输出 | 2 | 60 | 20 min |
| **P5** | 3 个零改动策略 YAML | 3 | 0（YAML only） | 15 min |
| **P6** | 策略治理（默认列表） | 1 | 5 | 5 min |
| **P7** | get_fundamental_profile 工具 | 1 | 80 | 25 min |
| **P8** | get_fund_flow 工具 | 1 | 60 | 20 min |
| **P9** | 2 个需新工具的策略 YAML | 2 | 0（YAML only） | 10 min |
| **P10** | 测试 + 验证 | 2 | 80 | 20 min |
| **合计** | | 15 文件 | ~345 行 | ~2.5 小时 |
