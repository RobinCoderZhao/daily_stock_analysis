# SaaS Phase 5：管理员控制台

> 本阶段目标：构建平台管理能力——用户管理、订阅管理、平台 API Key 管理、数据看板。
> 前置条件：Phase 4 完成（订阅/支付可用）
> 预计工期：2 周

---

## 1. 管理员权限控制

### 1.1 角色校验中间件

#### [NEW] `api/middlewares/admin.py`

```python
"""Admin role enforcement for /admin/* routes."""

async def admin_required(request: Request, call_next):
    if not request.url.path.startswith("/api/v1/admin"):
        return await call_next(request)

    role = getattr(request.state, "user_role", None)
    if role not in ("admin", "super_admin"):
        return JSONResponse(403, {"error": "admin_required"})
    return await call_next(request)

def super_admin_required(request: Request):
    """Dependency for super_admin-only routes (API Key management)."""
    role = getattr(request.state, "user_role", None)
    if role != "super_admin":
        raise HTTPException(403, detail="super_admin_required")
```

---

## 2. 用户管理 API

#### [NEW] `api/v1/endpoints/admin/users.py`

```python
router = APIRouter(prefix="/admin/users", tags=["admin"])

@router.get("/")
async def list_users(page: int = 1, limit: int = 20, search: str = None):
    """Paginated user list with search by email/nickname."""
    ...

@router.get("/{user_id}")
async def get_user_detail(user_id: int):
    """User detail with subscription, usage stats."""
    ...

@router.put("/{user_id}/status")
async def update_user_status(user_id: int, body: UpdateStatusRequest):
    """Suspend / reactivate user."""
    ...

@router.put("/{user_id}/subscription")
async def adjust_subscription(user_id: int, body: AdjustSubRequest):
    """Manually adjust subscription tier / credits."""
    ...
```

---

## 3. 平台 API Key 管理

### 3.1 加密存储

#### [NEW] `src/services/platform_key_service.py`

```python
"""Platform API Key management with AES-256-GCM encryption.

Master key from env: ENCRYPTION_MASTER_KEY
"""

class PlatformKeyService:
    """Manage platform LLM/search API keys."""

    def add_key(self, provider: str, raw_key: str, priority: int = 0,
                daily_limit: int = None) -> int:
        """Encrypt and store a new platform API key."""
        ...

    def get_active_key(self, provider: str) -> str:
        """Get decrypted active key with highest priority.
        Implements round-robin if multiple keys exist.
        """
        ...

    def list_keys(self, provider: str = None) -> List[Dict]:
        """List keys (masked, no raw values returned)."""
        ...

    def deactivate_key(self, key_id: int) -> bool: ...

    def rotate_daily_counts(self) -> None:
        """Reset used_today counters (daily cron)."""
        ...
```

### 3.2 数据模型

#### [NEW] 在 `src/models/` 新增

```python
class PlatformApiKey(Base):
    __tablename__ = "platform_api_keys"

    id = Column(Integer, primary_key=True)
    provider = Column(String(32), nullable=False, index=True)
    encrypted_key = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)
    daily_limit = Column(Integer, nullable=True)
    used_today = Column(Integer, default=0)
    label = Column(String(100), nullable=True)  # Human-readable label
    last_rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
```

### 3.3 API

#### [NEW] `api/v1/endpoints/admin/keys.py`

```python
router = APIRouter(prefix="/admin/keys", tags=["admin"],
                   dependencies=[Depends(super_admin_required)])

@router.get("/")
async def list_keys(): ...

@router.post("/")
async def add_key(body: AddKeyRequest): ...

@router.put("/{key_id}/deactivate")
async def deactivate_key(key_id: int): ...

@router.get("/usage")
async def key_usage_stats(): ...
```

---

## 4. 数据看板

### 4.1 看板 API

#### [NEW] `api/v1/endpoints/admin/dashboard.py`

```python
router = APIRouter(prefix="/admin/dashboard", tags=["admin"])

@router.get("/overview")
async def get_overview():
    """Key metrics: total users, active today, revenue, LLM cost, etc."""
    ...

@router.get("/user-growth")
async def user_growth(days: int = 30):
    """User registration trend (daily counts)."""
    ...

@router.get("/usage-stats")
async def usage_stats(days: int = 30):
    """Analysis count, agent chat count by day."""
    ...

@router.get("/revenue")
async def revenue_stats(days: int = 30):
    """Payment revenue by day, by plan."""
    ...

@router.get("/llm-cost")
async def llm_cost_stats(days: int = 30):
    """LLM token usage and estimated cost by model."""
    ...
```

---

## 5. 前端管理页面

### 5.1 路由

#### [MODIFY] `apps/dsa-web/src/App.tsx`

```typescript
// Admin routes (role-gated)
<Route path="/admin/dashboard" element={<AdminDashboard />} />
<Route path="/admin/users" element={<AdminUsers />} />
<Route path="/admin/keys" element={<AdminKeys />} />
```

### 5.2 页面

| 文件 | 功能 |
|------|------|
| `AdminDashboard.tsx` | 数据看板（图表：Recharts） |
| `AdminUsers.tsx` | 用户列表 + 搜索 + 操作 |
| `AdminKeys.tsx` | 平台 Key 管理 |

### 5.3 导航栏

管理员用户在侧边栏显示"管理"入口（仅 admin/super_admin 可见）。

---

## 6. 系统配置迁移

#### [MODIFY] `apps/dsa-web/src/pages/SettingsPage.tsx`

- 普通用户：只看到个人设置（自选股、昵称、密码）
- 管理员：额外显示系统配置入口（跳转 `/admin/config`）

原 SettingsPage 中的 `.env` 管理功能迁移到 `/admin/config` 路由。

---

## 7. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| NEW | `api/middlewares/admin.py` | 管理员权限中间件 |
| NEW | `api/v1/endpoints/admin/users.py` | 用户管理 API |
| NEW | `api/v1/endpoints/admin/keys.py` | Key 管理 API |
| NEW | `api/v1/endpoints/admin/dashboard.py` | 数据看板 API |
| NEW | `src/services/platform_key_service.py` | 平台 Key 加密服务 |
| NEW | `src/models/platform_key.py` | PlatformApiKey 模型 |
| NEW | `apps/dsa-web/src/pages/admin/AdminDashboard.tsx` | 看板页 |
| NEW | `apps/dsa-web/src/pages/admin/AdminUsers.tsx` | 用户管理页 |
| NEW | `apps/dsa-web/src/pages/admin/AdminKeys.tsx` | Key 管理页 |
| MODIFY | `apps/dsa-web/src/App.tsx` | 管理路由 |
| MODIFY | `apps/dsa-web/src/pages/SettingsPage.tsx` | 角色分流 |
| MODIFY | `.env.example` | ENCRYPTION_MASTER_KEY |
| MODIFY | `requirements.txt` | 新增 cryptography |

---

## 8. 验收标准

- [ ] 管理员可搜索/冻结/解冻用户
- [ ] 管理员可手动调整订阅等级和配额
- [ ] 平台 API Key 加密存储，管理界面显示掩码值
- [ ] 数据看板展示用户增长、调用量、收入、LLM 成本
- [ ] 普通用户访问 /admin/* 返回 403
- [ ] super_admin 才能操作 Key 管理
