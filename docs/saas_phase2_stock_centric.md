# SaaS Phase 2：Stock-Centric 架构 + 数据隔离

> 本阶段目标：实现以股票为中心的分析去重架构，为所有用户私有表添加 `user_id` 隔离，用户自选股替代全局 `STOCK_LIST`。
> 前置条件：Phase 1 完成（用户注册/JWT 可用）
> 预计工期：2-3 周

---

## 1. 全局分析去重层

### 1.1 数据模型

#### [NEW] `src/models/stock_analysis.py`

```python
"""Stock-centric analysis deduplication layer."""

from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, DateTime, Date, ForeignKey,
    UniqueConstraint, Index,
)
from src.storage import Base


class StockAnalysisDaily(Base):
    """Global per-stock per-day analysis state.

    Ensures each stock is analyzed at most once per day,
    regardless of how many users watch it.

    Status lifecycle: pending → analyzing → completed / failed
    """
    __tablename__ = "stock_analysis_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False)
    analysis_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    result_id = Column(
        Integer,
        ForeignKey("analysis_history.id"),
        nullable=True,
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("code", "analysis_date", name="uix_stock_analysis_daily"),
        Index("ix_sad_date_status", "analysis_date", "status"),
    )
```

### 1.2 调度器改造

#### [MODIFY] `main.py`（第 269 行附近 `scheduled_task()`）

改造定时分析逻辑：

```python
def scheduled_task():
    """SaaS mode: collect all active users' watchlists, deduplicate, analyze."""
    if config.saas_mode:
        from src.services.analysis_scheduler import AnalysisScheduler
        scheduler = AnalysisScheduler()
        scheduler.run_daily_analysis()
    else:
        # Original logic: analyze STOCK_LIST from .env
        run_analysis(config.stock_list, ...)
```

#### [NEW] `src/services/analysis_scheduler.py`

```python
"""Orchestrate daily analysis with cross-user deduplication."""

class AnalysisScheduler:
    """Collect all users' watchlists → deduplicate → analyze each stock once."""

    def run_daily_analysis(self) -> Dict[str, Any]:
        """Main entry point for daily scheduled analysis.

        1. Query all active users with valid subscriptions
        2. Collect union of all watchlist codes → unique set
        3. For each unique code:
           a. Check stock_analysis_daily for today
           b. If completed → skip
           c. If analyzing → skip (another worker is on it)
           d. If pending/missing → mark 'analyzing', run analysis, mark 'completed'
        4. Return summary {analyzed: N, skipped: N, failed: N}
        """
        ...

    def _get_active_stock_codes(self) -> List[str]:
        """Get deduplicated list of stock codes from all active users.

        Active user = status='active' AND subscription not expired.
        Free users: only if within 7-day trial period.
        """
        ...

    def _analyze_stock(self, code: str, analysis_date: date) -> bool:
        """Analyze a single stock with locking.

        Uses SELECT ... FOR UPDATE (PostgreSQL) or INSERT ... ON CONFLICT
        to prevent double-analysis if multiple workers run concurrently.
        """
        ...
```

### 1.3 用户查看报告

#### [MODIFY] `api/v1/endpoints/history.py`

用户查看报告时，改为从全局 `stock_analysis_daily` 查询：

```python
@router.get("/stock/{code}/latest")
async def get_stock_latest_report(
    code: str,
    request: Request,
    service: HistoryService = Depends(),
):
    """Get latest analysis report for a stock.

    SaaS mode: verify user has this stock in watchlist or is doing temp analysis.
    Then look up stock_analysis_daily → return shared result.
    """
    if _is_saas_mode():
        user_id = request.state.user_id
        _verify_watchlist_access(user_id, code)

    record = service.get_latest_shared_analysis(code)
    if not record:
        raise HTTPException(404, detail="no_analysis_available")
    return record
```

---

## 2. 用户自选股

### 2.1 数据模型

#### 在 `src/models/user.py` 新增

```python
class UserWatchlist(Base):
    """User's stock watchlist entries."""
    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    group_name = Column(String(50), nullable=False, default="默认分组")
    code = Column(String(10), nullable=False)
    name = Column(String(50), nullable=True)
    market = Column(String(10), nullable=False, default="cn")
    sort_order = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uix_watchlist_user_code"),
        Index("ix_watchlist_user_group", "user_id", "group_name"),
    )
```

### 2.2 自选股服务

#### [NEW] `src/services/watchlist_service.py`

```python
"""User watchlist management with subscription-based limits."""

class WatchlistService:
    """CRUD for user watchlists with quota enforcement."""

    def add_stock(self, user_id: int, code: str, name: str = None,
                  group: str = "默认分组") -> Dict[str, Any]:
        """Add stock to user's watchlist.

        - Check subscription watchlist_limit (free=3, standard=20, pro=100)
        - Validate stock code format
        - Check uniqueness
        - Auto-resolve stock name if not provided
        """
        ...

    def remove_stock(self, user_id: int, code: str) -> bool:
        """Remove stock from watchlist."""
        ...

    def get_watchlist(self, user_id: int, group: str = None) -> List[Dict]:
        """Get user's watchlist, optionally filtered by group."""
        ...

    def get_groups(self, user_id: int) -> List[str]:
        """Get user's watchlist group names."""
        ...

    def reorder(self, user_id: int, code_order: List[str]) -> None:
        """Update sort_order for stocks."""
        ...
```

### 2.3 自选股 API

#### [NEW] `api/v1/endpoints/watchlist.py`

```python
router = APIRouter(prefix="/watchlist", tags=["watchlist"])

@router.get("/")
async def get_watchlist(request: Request): ...

@router.post("/add")
async def add_stock(request: Request, body: AddStockRequest): ...

@router.delete("/{code}")
async def remove_stock(request: Request, code: str): ...

@router.get("/groups")
async def get_groups(request: Request): ...

@router.put("/reorder")
async def reorder(request: Request, body: ReorderRequest): ...
```

---

## 3. 私有表 user_id 隔离

### 3.1 数据库迁移

#### Alembic 迁移脚本

为以下表添加 `user_id` 列（可 NULL，过渡期兼容旧数据）：

| 表名 | 改动 |
|------|------|
| `analysis_history` | 新增 `user_id INTEGER`（SaaS 模式下必填） |
| `conversation_messages` | 新增 `user_id INTEGER` |
| `news_intel` | 新增 `user_id INTEGER` |
| `backtest_results` | 新增 `user_id INTEGER` |
| `backtest_summaries` | 新增 `user_id INTEGER` |
| `signals` | 新增 `user_id INTEGER` |
| `llm_usage` | 新增 `user_id INTEGER` |

```python
# migrations/versions/xxxx_add_user_id_columns.py
def upgrade():
    for table in [
        "analysis_history", "conversation_messages", "news_intel",
        "backtest_results", "backtest_summaries", "signals", "llm_usage",
    ]:
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
```

### 3.2 服务层注入

#### [MODIFY] 所有 src/services/*.py

每个服务类的查询方法添加 `user_id` 参数，SaaS 模式下强制过滤：

```python
# 通用模式
def _apply_user_filter(query, model, user_id: int):
    """Apply user isolation filter in SaaS mode."""
    if Config.get_instance().saas_mode and user_id:
        query = query.filter(model.user_id == user_id)
    return query
```

受影响的服务文件及方法：

| 服务文件 | 需修改方法 |
|----------|-----------|
| `history_service.py` | `get_list()`, `resolve_and_get_detail()`, `search()` |
| `analysis_service.py` | `analyze_stock()` — 写入时关联 user_id |
| `signal_service.py` | `get_active_signals()`, `create_signal_from_report()` |
| `backtest_service.py` | `get_results()`, `get_summary()` |
| `task_service.py` | `get_tasks()` |
| `task_queue.py` | `submit_task()` — 关联 user_id |

### 3.3 API 端点注入

#### [MODIFY] 所有 api/v1/endpoints/*.py

从 `request.state.user_id` 获取用户 ID 注入服务调用：

```python
@router.get("/history")
async def get_history(request: Request, service: HistoryService = Depends()):
    user_id = getattr(request.state, "user_id", None)
    return service.get_list(user_id=user_id, ...)
```

---

## 4. 前端改造

### 4.1 首页

#### [MODIFY] `apps/dsa-web/src/pages/HomePage.tsx`

- 从 API 获取用户自选股列表（替代硬编码或全局列表）
- 显示每只自选股的最新分析结果
- 添加"管理自选"入口

### 4.2 设置页

#### [MODIFY] `apps/dsa-web/src/pages/SettingsPage.tsx`

- 分为"个人设置"（自选股、昵称、密码）和"系统设置"（仅管理员可见）
- 自选股管理卡片：添加/删除/分组/排序

### 4.3 新增自选股 API 客户端

#### [NEW] `apps/dsa-web/src/api/watchlist.ts`

```typescript
export const getWatchlist = () => api.get('/watchlist');
export const addStock = (code: string) => api.post('/watchlist/add', { code });
export const removeStock = (code: string) => api.delete(`/watchlist/${code}`);
```

---

## 5. 测试计划

### 5.1 单元测试

#### [NEW] `tests/test_analysis_scheduler.py`

- 多用户自选同一只股票 → 只分析一次
- 已完成分析 → 跳过
- 分析中状态 → 等待
- 免费用户过期 → 不纳入分析池

#### [NEW] `tests/test_watchlist_service.py`

- 添加超过配额限制 → 报错
- 重复添加 → 报错
- 不同用户独立管理

### 5.2 集成测试

```bash
python -m pytest tests/test_analysis_scheduler.py tests/test_watchlist_service.py -v
alembic upgrade head  # 验证迁移
```

---

## 6. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| NEW | `src/models/stock_analysis.py` | StockAnalysisDaily 模型 |
| NEW | `src/services/analysis_scheduler.py` | 去重调度器 |
| NEW | `src/services/watchlist_service.py` | 自选股服务 |
| NEW | `api/v1/endpoints/watchlist.py` | 自选股 API |
| NEW | `apps/dsa-web/src/api/watchlist.ts` | 前端 API 客户端 |
| NEW | `tests/test_analysis_scheduler.py` | 调度器测试 |
| NEW | `tests/test_watchlist_service.py` | 自选股测试 |
| NEW | `migrations/versions/xxxx_add_stock_analysis_daily.py` | 迁移 |
| NEW | `migrations/versions/xxxx_add_user_id_columns.py` | 迁移 |
| MODIFY | `src/models/user.py` | 新增 UserWatchlist |
| MODIFY | `main.py` | 调度器分支 |
| MODIFY | `api/v1/endpoints/history.py` | 共享分析结果查询 |
| MODIFY | `src/services/history_service.py` | user_id 过滤 |
| MODIFY | `src/services/analysis_service.py` | user_id 写入 |
| MODIFY | `src/services/signal_service.py` | user_id 过滤 |
| MODIFY | `src/services/backtest_service.py` | user_id 过滤 |
| MODIFY | `src/services/task_queue.py` | user_id 关联 |
| MODIFY | `apps/dsa-web/src/pages/HomePage.tsx` | 用户自选展示 |
| MODIFY | `apps/dsa-web/src/pages/SettingsPage.tsx` | 个人设置拆分 |

---

## 7. 验收标准

- [ ] 多用户关注同一股票，每日只执行一次 LLM 分析
- [ ] `stock_analysis_daily` 正确维护分析状态生命周期
- [ ] 用户只能看到自己的对话、回测、信号数据
- [ ] `analysis_history` 通过 `stock_analysis_daily` 全局共享
- [ ] 自选股增删改查 API 正常工作，配额限制生效
- [ ] `SAAS_MODE=false` 时所有行为与改造前一致
