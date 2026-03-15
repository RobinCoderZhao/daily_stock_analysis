# SaaS Phase 1：安全加固 + 用户注册 + JWT 认证

> 本阶段目标：修复安全审计漏洞，建立多用户注册/登录体系，用 JWT 替换 Cookie Session。
> 预计工期：2-3 周
> 分支：`feature/saas-multi-tenant`

---

## 1. 安全漏洞修复

### 1.1 Config API 敏感值掩码

#### [MODIFY] `src/services/system_config_service.py`

`get_config()` 方法（第 49-77 行）当前直接返回所有敏感值明文，需添加服务端掩码：

```python
def get_config(self, include_schema: bool = True, mask_token: str = "******") -> Dict[str, Any]:
    config_map = self._manager.read_config_map()
    # ... existing code ...

    items: List[Dict[str, Any]] = []
    for key in all_keys:
        raw_value = config_map.get(key, "")
        field_schema = schema_by_key[key]
        # NEW: server-side masking for sensitive fields
        is_sensitive = bool(field_schema.get("is_sensitive", False))
        if is_sensitive and raw_value:
            display_value = mask_token
            is_masked = True
        else:
            display_value = raw_value
            is_masked = False

        item: Dict[str, Any] = {
            "key": key,
            "value": display_value,    # was: raw_value
            "raw_value_exists": bool(raw_value),
            "is_masked": is_masked,    # was: False
        }
        if include_schema:
            item["schema"] = field_schema
        items.append(item)
```

前端无需修改 — `useSystemConfig.ts` 和 `SettingsField.tsx` 已支持 `isMasked` / `maskToken` 协议。

### 1.2 CORS 加固

#### [MODIFY] `api/app.py`（第 94-103 行）

```python
    if os.environ.get("CORS_ALLOW_ALL", "").lower() == "true":
        import logging
        logging.getLogger(__name__).warning(
            "CORS_ALLOW_ALL=true is deprecated. Use CORS_ORIGINS instead."
        )
        allowed_origins = ["*"]
        allow_credentials = False  # NEW: wildcard + credentials is insecure
    else:
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,  # was: always True
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

### 1.3 Swagger 文档保护

#### [MODIFY] `api/app.py`（第 63 行附近）

```python
    _auth_on = os.environ.get("ADMIN_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
    _docs_url = None if _auth_on else "/docs"
    _redoc_url = None if _auth_on else "/redoc"

    app = FastAPI(
        title="Daily Stock Analysis API",
        docs_url=_docs_url,    # NEW
        redoc_url=_redoc_url,  # NEW
        # ...
    )
```

### 1.4 Auth 中间件清理

#### [MODIFY] `api/middlewares/auth.py`

移除 `/docs`、`/redoc`、`/openapi.json` 的豁免：

```python
EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/status",
    "/api/v1/auth/logout",
    "/api/health",
    "/health",
    # /docs, /redoc, /openapi.json REMOVED
})
```

### 1.5 启动安全警告

#### [MODIFY] `api/app.py`

在 `create_app()` 末尾添加：

```python
    _host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    if not _auth_on and _host == "0.0.0.0":
        import logging
        logging.getLogger(__name__).warning(
            "SECURITY WARNING: Auth is DISABLED but listening on 0.0.0.0. "
            "All APIs including config with API keys are publicly accessible."
        )
```

### 1.6 测试更新

#### [MODIFY] `tests/test_system_config_service.py`

```python
    # 旧测试（验证明文 → 改为验证掩码）
    def test_get_config_masks_sensitive_values(self) -> None:
        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}
        self.assertIn("GEMINI_API_KEY", items)
        self.assertEqual(items["GEMINI_API_KEY"]["value"], "******")  # was: "secret-key-value"
        self.assertTrue(items["GEMINI_API_KEY"]["is_masked"])         # was: assertFalse
        self.assertTrue(items["GEMINI_API_KEY"]["raw_value_exists"])

    # 新增：非敏感字段不掩码
    def test_get_config_non_sensitive_unmasked(self) -> None:
        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["STOCK_LIST"]["value"], "600519,000001")
        self.assertFalse(items["STOCK_LIST"]["is_masked"])
```

#### [MODIFY] `tests/test_system_config_api.py`

同步更新 `test_get_config_returns_raw_secret_value` → `test_get_config_masks_secret_value`。

---

## 2. PostgreSQL 迁移

### 2.1 依赖安装

```bash
pip install psycopg2-binary alembic
```

#### [MODIFY] `requirements.txt`

新增：
```
psycopg2-binary>=2.9.9
alembic>=1.13.0
```

### 2.2 数据库连接配置

#### [MODIFY] `src/config.py`

新增配置字段：

```python
@dataclass
class Config:
    # ... existing fields ...

    # Database
    database_url: str = ""  # PostgreSQL: postgresql://user:pass@host:port/dbname
    saas_mode: bool = False
```

解析逻辑：
```python
database_url = os.getenv("DATABASE_URL", "")
saas_mode = os.getenv("SAAS_MODE", "").lower() in ("true", "1", "yes")

# Backward compatibility: if no DATABASE_URL, use SQLite
if not database_url:
    db_path = os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    database_url = f"sqlite:///{db_path}"
```

#### [MODIFY] `.env.example`

新增：
```ini
# === SaaS Mode ===
SAAS_MODE=false
DATABASE_URL=postgresql://dsa_user:password@localhost:5432/dsa_db
```

### 2.3 Alembic 初始化

```bash
cd /Users/robin/myworkdir/daily_stock_analysis
alembic init migrations
```

#### [MODIFY] `migrations/env.py`

配置 target_metadata：
```python
from src.storage import Base
target_metadata = Base.metadata
```

#### [MODIFY] `alembic.ini`

```ini
sqlalchemy.url = %(DATABASE_URL)s
```

### 2.4 Storage 层改造

#### [MODIFY] `src/storage.py`

将 `DatabaseManager` 的 `create_engine` 改为支持 PostgreSQL：

```python
class DatabaseManager:
    def __init__(self, db_url: str = None):
        if db_url is None:
            config = get_config()
            db_url = config.database_url

        self._engine = create_engine(
            db_url,
            pool_pre_ping=True,
            # PostgreSQL specific
            pool_size=10 if "postgresql" in db_url else 1,
            max_overflow=20 if "postgresql" in db_url else 0,
        )
```

---

## 3. 用户表与注册/登录

### 3.1 用户数据模型

#### [NEW] `src/models/user.py`

```python
"""User and subscription data models."""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Date, Text,
    UniqueConstraint, Index,
)
from src.storage import Base


class User(Base):
    """Platform user account."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True)
    nickname = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    role = Column(String(20), nullable=False, default="user")
    # role: user / admin / super_admin
    status = Column(String(20), nullable=False, default="active")
    # status: active / suspended / deleted
    created_at = Column(DateTime, default=datetime.now, index=True)
    last_login_at = Column(DateTime, nullable=True)
    oauth_provider = Column(String(32), nullable=True)
    oauth_id = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_user_email_status", "email", "status"),
    )


class Subscription(Base):
    """User subscription record."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    tier = Column(String(20), nullable=False, default="free")
    # tier: free / standard / pro
    status = Column(String(20), nullable=False, default="active")
    # status: active / expired / cancelled
    watchlist_limit = Column(Integer, nullable=False, default=3)
    start_at = Column(DateTime, default=datetime.now)
    expire_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("ix_sub_user_status", "user_id", "status"),
    )
```

### 3.2 用户服务层

#### [NEW] `src/services/user_service.py`

```python
"""User registration, login, and profile management."""

import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class UserService:
    """Manage user lifecycle."""

    def register(self, email: str, password: str, nickname: str = None) -> Dict[str, Any]:
        """Register a new user with email + password.

        - Validate email format and uniqueness
        - Hash password with PBKDF2-SHA256
        - Create user record with role='user', status='active'
        - Create free subscription (7-day expiry)
        - Return user info (no password hash)
        """
        ...

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return JWT tokens.

        - Verify email exists and status is active
        - Check rate limit (5 failures per 5 minutes per IP)
        - Verify password hash
        - Generate access_token (15min) + refresh_token (7days)
        - Update last_login_at
        """
        ...

    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Generate new access_token from valid refresh_token."""
        ...

    def get_profile(self, user_id: int) -> Dict[str, Any]:
        """Return user profile with subscription info."""
        ...

    def update_profile(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """Update nickname, avatar_url, etc."""
        ...

    def change_password(self, user_id: int, old_password: str,
                        new_password: str) -> bool:
        """Change password after verifying old password."""
        ...
```

### 3.3 JWT 认证模块

#### [NEW] `src/jwt_auth.py`

```python
"""JWT token generation and verification.

Uses PyJWT with HS256 algorithm.
Secret key from environment variable JWT_SECRET_KEY.
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_access_token(user_id: int, role: str) -> str:
    """Create short-lived access token."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")

def create_refresh_token(user_id: int) -> str:
    """Create long-lived refresh token (stored in HttpOnly cookie)."""
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")

def verify_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        if payload.get("type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def _get_secret() -> str:
    import os
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise ValueError("JWT_SECRET_KEY environment variable is required")
    return secret
```

#### [MODIFY] `requirements.txt`

新增：
```
PyJWT>=2.8.0
```

#### [MODIFY] `.env.example`

新增：
```ini
JWT_SECRET_KEY=your-random-secret-at-least-32-chars
```

---

## 4. Auth 中间件改造

### 4.1 双模式中间件

#### [MODIFY] `api/middlewares/auth.py`

改造为支持两种模式：

```python
"""Authentication middleware.

SAAS_MODE=true:  JWT Bearer token authentication (multi-user)
SAAS_MODE=false: Original cookie session authentication (single admin)
"""

EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/register",  # NEW
    "/api/v1/auth/status",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",   # NEW
    "/api/health",
    "/health",
})

async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Skip exempt paths and static files
    if path in EXEMPT_PATHS or not path.startswith("/api/"):
        return await call_next(request)

    if _is_saas_mode():
        return await _jwt_auth(request, call_next)
    else:
        return await _cookie_auth(request, call_next)

async def _jwt_auth(request, call_next):
    """JWT Bearer token verification."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "missing_token"})

    token = auth_header[7:]
    payload = verify_token(token, expected_type="access")
    if payload is None:
        return JSONResponse(status_code=401, content={"error": "invalid_token"})

    # Inject user context into request state
    request.state.user_id = int(payload["sub"])
    request.state.user_role = payload["role"]
    return await call_next(request)

async def _cookie_auth(request, call_next):
    """Original cookie session authentication (backward compatible)."""
    # ... existing auth logic unchanged ...
```

---

## 5. Auth API 端点

#### [MODIFY] `api/v1/endpoints/auth.py`

新增注册、刷新、用户信息接口：

```python
# Existing endpoints (keep):
# POST /api/v1/auth/login
# POST /api/v1/auth/logout
# GET  /api/v1/auth/status

# New endpoints (SaaS mode only):
@router.post("/register")
async def register(request: RegisterRequest, service: UserService = Depends()):
    """User registration with email + password."""
    result = service.register(
        email=request.email,
        password=request.password,
        nickname=request.nickname,
    )
    return RegisterResponse(**result)

@router.post("/refresh")
async def refresh_token(request: Request, service: UserService = Depends()):
    """Refresh access token using refresh token from HttpOnly cookie."""
    refresh = request.cookies.get("dsa_refresh_token")
    if not refresh:
        raise HTTPException(401, detail="missing_refresh_token")
    result = service.refresh_token(refresh)
    response = JSONResponse(content={"access_token": result["access_token"]})
    # Update refresh token cookie
    _set_refresh_cookie(response, result["refresh_token"])
    return response

@router.get("/me")
async def get_profile(request: Request, service: UserService = Depends()):
    """Get current user profile with subscription info."""
    user_id = request.state.user_id
    return service.get_profile(user_id)
```

#### [NEW] `api/v1/schemas/auth.py`

```python
from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str | None = None

class RegisterResponse(BaseModel):
    user_id: int
    email: str
    access_token: str

class ProfileResponse(BaseModel):
    user_id: int
    email: str
    nickname: str | None
    role: str
    tier: str
    watchlist_limit: int
    expire_at: str | None
    created_at: str
```

---

## 6. 前端改造

### 6.1 登录页增加注册

#### [MODIFY] `apps/dsa-web/src/pages/LoginPage.tsx`

改造为注册 + 登录双模式：

- 新增 `isRegister` 状态切换
- 注册模式显示邮箱 + 密码 + 确认密码 + 昵称
- 登录模式保持原有邮箱 + 密码
- 调用对应 API（`/auth/register` 或 `/auth/login`）

### 6.2 AuthContext 改造

#### [MODIFY] `apps/dsa-web/src/contexts/AuthContext.tsx`

SaaS 模式下：
- 登录后将 `access_token` 存入内存状态（非 localStorage）
- `refresh_token` 通过 HttpOnly Cookie 自动管理
- 添加 `useEffect` 定时刷新 access_token（每 12 分钟）
- 暴露 `user` 对象（包含 `role`、`tier`）

### 6.3 API 请求拦截器

#### [MODIFY] `apps/dsa-web/src/api/index.ts`

所有 API 请求自动附带 `Authorization: Bearer {token}`：

```typescript
const api = axios.create({ baseURL: '/api/v1' });

api.interceptors.request.use((config) => {
  const token = getAccessToken();  // from AuthContext
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(null, async (error) => {
  if (error.response?.status === 401 && !error.config._retry) {
    error.config._retry = true;
    await refreshAccessToken();
    return api(error.config);
  }
  throw error;
});
```

---

## 7. 测试计划

### 7.1 安全修复测试

```bash
# Unit tests
python -m pytest tests/test_system_config_service.py tests/test_system_config_api.py -v

# Syntax check
python -m py_compile src/services/system_config_service.py
python -m py_compile api/app.py
python -m py_compile api/middlewares/auth.py
```

### 7.2 用户注册/登录测试

#### [NEW] `tests/test_user_service.py`

覆盖：
- 正常注册 → 返回用户信息 + JWT
- 重复邮箱注册 → 报错
- 登录正确密码 → 返回 token
- 登录错误密码 → 报错
- 登录频率限制 → 超过 5 次锁定
- 刷新 token → 返回新 access_token
- 过期 token → 401

#### [NEW] `tests/test_jwt_auth.py`

覆盖：
- create_access_token → 可正确解码
- create_refresh_token → type=refresh
- verify_token 过期 → 返回 None
- verify_token type 不匹配 → 返回 None

### 7.3 前端测试

```bash
cd apps/dsa-web && npm run build
```

验证 TypeScript 编译无错误。

---

## 8. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| MODIFY | `src/services/system_config_service.py` | Config API 敏感值掩码 |
| MODIFY | `api/app.py` | CORS 加固 + Swagger 保护 + 启动警告 |
| MODIFY | `api/middlewares/auth.py` | 双模式中间件 + 移除 /docs 豁免 |
| MODIFY | `src/config.py` | 新增 database_url / saas_mode 字段 |
| MODIFY | `src/storage.py` | DatabaseManager 支持 PostgreSQL |
| MODIFY | `.env.example` | 新增 SAAS_MODE / DATABASE_URL / JWT_SECRET_KEY |
| MODIFY | `requirements.txt` | 新增 psycopg2-binary / alembic / PyJWT |
| MODIFY | `api/v1/endpoints/auth.py` | 新增 register / refresh / me 接口 |
| MODIFY | `apps/dsa-web/src/pages/LoginPage.tsx` | 注册 + 登录双模式 |
| MODIFY | `apps/dsa-web/src/contexts/AuthContext.tsx` | JWT 管理 |
| NEW | `src/models/user.py` | User / Subscription 数据模型 |
| NEW | `src/services/user_service.py` | 用户注册/登录服务 |
| NEW | `src/jwt_auth.py` | JWT 生成和验证 |
| NEW | `api/v1/schemas/auth.py` | 注册/登录 Pydantic schemas |
| NEW | `migrations/` | Alembic 迁移框架 |
| NEW | `tests/test_user_service.py` | 用户服务测试 |
| NEW | `tests/test_jwt_auth.py` | JWT 测试 |
| MODIFY | `tests/test_system_config_service.py` | 掩码测试更新 |
| MODIFY | `tests/test_system_config_api.py` | 掩码测试更新 |

---

## 9. 验收标准

- [ ] 所有 5 个安全漏洞已修复并通过测试
- [ ] PostgreSQL 连接可用，Alembic 迁移执行成功
- [ ] 用户可注册新账号（邮箱 + 密码）
- [ ] 用户可登录并获得 JWT
- [ ] JWT 过期后自动刷新
- [ ] `SAAS_MODE=false` 时原有行为完全不受影响
- [ ] 前端登录页支持注册 + 登录切换
- [ ] 前端所有 API 请求自动附带 Bearer token
