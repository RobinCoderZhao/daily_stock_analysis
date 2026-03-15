# SaaS Phase 4：订阅计费 + 支付集成

> 本阶段目标：实现免费/标准/专业三档订阅、配额中间件、Stripe 支付集成，预留微信/支付宝适配。
> 前置条件：Phase 2 完成（用户体系 + 自选股配额）
> 预计工期：2-3 周

---

## 1. 订阅模型

### 1.1 数据模型

#### [MODIFY] `src/models/user.py`

在 Phase 1 创建的 `Subscription` 模型基础上扩展：

```python
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    tier = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    watchlist_limit = Column(Integer, nullable=False, default=3)
    daily_analysis_limit = Column(Integer, nullable=True)  # None = unlimited
    agent_daily_limit = Column(Integer, nullable=True)
    start_at = Column(DateTime, default=datetime.now)
    expire_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    # Temporary analysis credits (pay-per-use, never expire)
    temp_analysis_credits = Column(Integer, nullable=False, default=0)
```

#### [NEW] 新增 `PaymentOrder` 和 `UsageRecord`

```python
class PaymentOrder(Base):
    """Payment order record."""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False)
    plan = Column(String(32), nullable=False)
    # plan: standard_monthly / pro_monthly / temp_10 / temp_50 ...
    amount_cents = Column(Integer, nullable=False)  # 金额（分）
    currency = Column(String(8), nullable=False, default="CNY")
    payment_provider = Column(String(32))  # stripe / wechat / alipay
    payment_provider_id = Column(String(255))  # Stripe session id etc.
    status = Column(String(20), nullable=False, default="pending")
    # status: pending / paid / refunded / failed / expired
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class UsageRecord(Base):
    """Per-action usage tracking for billing and analytics."""
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(32), nullable=False)
    # action: analysis / agent_chat / backtest / temp_analysis
    stock_code = Column(String(16), nullable=True)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_usage_user_date", "user_id", "created_at"),
    )
```

### 1.2 订阅等级配置

```python
TIER_CONFIG = {
    "free": {
        "watchlist_limit": 3,
        "daily_analysis_limit": None,   # Auto-analysis for watchlist (no cap)
        "agent_daily_limit": 0,         # No agent chat
        "trial_days": 7,
        "features": ["basic_analysis"],
    },
    "standard": {
        "watchlist_limit": 20,
        "daily_analysis_limit": None,
        "agent_daily_limit": 10,
        "features": ["basic_analysis", "agent_chat", "backtest", "signals"],
    },
    "pro": {
        "watchlist_limit": 100,
        "daily_analysis_limit": None,
        "agent_daily_limit": None,      # Unlimited
        "features": ["basic_analysis", "agent_chat", "backtest", "signals",
                     "export", "api_access"],
    },
}
```

---

## 2. 配额中间件

#### [NEW] `api/middlewares/quota.py`

```python
"""Subscription quota enforcement middleware.

Checks:
1. Subscription validity (active + not expired)
2. Free trial expiry (7 days from registration)
3. Feature gating (agent chat, backtest, etc.)
4. Agent daily limits
"""

# Endpoint → required feature mapping
FEATURE_GATES = {
    "/api/v1/agent/chat": "agent_chat",
    "/api/v1/backtest/": "backtest",
    "/api/v1/signals/": "signals",
}

async def quota_middleware(request: Request, call_next):
    if not _is_saas_mode():
        return await call_next(request)

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return await call_next(request)

    path = request.url.path

    # 1. Check subscription validity
    sub = _get_active_subscription(user_id)
    if not sub:
        return JSONResponse(403, {"error": "subscription_expired"})

    # 2. Free trial check
    if sub.tier == "free" and sub.expire_at and datetime.now() > sub.expire_at:
        return JSONResponse(403, {"error": "free_trial_expired",
                                   "message": "免费试用已到期，请升级订阅"})

    # 3. Feature gating
    required_feature = _match_feature(path)
    if required_feature and required_feature not in TIER_CONFIG[sub.tier]["features"]:
        return JSONResponse(403, {"error": "feature_not_available",
                                   "message": f"此功能需要升级至更高会员等级"})

    # 4. Agent daily limit
    if required_feature == "agent_chat" and sub.agent_daily_limit is not None:
        used = _count_today_usage(user_id, "agent_chat")
        if used >= sub.agent_daily_limit:
            return JSONResponse(429, {"error": "agent_daily_limit_reached"})

    request.state.subscription = sub
    return await call_next(request)
```

---

## 3. 支付抽象层

#### [NEW] `src/payment/base.py`

```python
"""Payment provider abstract interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CheckoutResult:
    checkout_url: str
    provider_session_id: str

@dataclass
class WebhookEvent:
    event_type: str      # checkout.completed / payment.refunded
    order_no: str
    amount_cents: int
    provider_data: dict

@dataclass
class RefundResult:
    success: bool
    refund_id: str

class PaymentProvider(ABC):
    @abstractmethod
    async def create_checkout(self, order: "PaymentOrder") -> CheckoutResult: ...

    @abstractmethod
    async def verify_webhook(self, payload: bytes, headers: dict) -> WebhookEvent: ...

    @abstractmethod
    async def refund(self, order_no: str, amount_cents: int) -> RefundResult: ...
```

#### [NEW] `src/payment/stripe_provider.py`

```python
"""Stripe Checkout integration."""

import stripe
from src.payment.base import PaymentProvider, CheckoutResult, WebhookEvent, RefundResult

class StripeProvider(PaymentProvider):

    def __init__(self):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        self._webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    async def create_checkout(self, order) -> CheckoutResult:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": order.currency.lower(),
                    "product_data": {"name": _plan_display_name(order.plan)},
                    "unit_amount": order.amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            metadata={"order_no": order.order_no},
            success_url=f"{_get_base_url()}/payment/success?order={order.order_no}",
            cancel_url=f"{_get_base_url()}/payment/cancel",
        )
        return CheckoutResult(
            checkout_url=session.url,
            provider_session_id=session.id,
        )

    async def verify_webhook(self, payload, headers) -> WebhookEvent:
        sig = headers.get("stripe-signature")
        event = stripe.Webhook.construct_event(payload, sig, self._webhook_secret)
        session = event["data"]["object"]
        return WebhookEvent(
            event_type=event["type"],
            order_no=session["metadata"]["order_no"],
            amount_cents=session["amount_total"],
            provider_data=dict(session),
        )

    async def refund(self, order_no, amount_cents) -> RefundResult:
        # Find payment intent from order, then refund
        ...
```

#### [NEW] `src/payment/wechat_provider.py`（预留桩）

```python
"""WeChat Pay provider stub — to be implemented when business license is ready."""

class WechatPayProvider(PaymentProvider):
    async def create_checkout(self, order): raise NotImplementedError("WeChat Pay not configured")
    async def verify_webhook(self, payload, headers): raise NotImplementedError
    async def refund(self, order_no, amount_cents): raise NotImplementedError
```

#### [NEW] `src/payment/alipay_provider.py`（预留桩）

同上模式。

---

## 4. 订阅服务层

#### [NEW] `src/services/subscription_service.py`

```python
class SubscriptionService:
    """Manage subscription lifecycle and payments."""

    def create_checkout(self, user_id: int, plan: str) -> Dict[str, Any]:
        """Create payment session.

        plan: 'standard_monthly' / 'pro_monthly' / 'temp_10'
        Returns: {checkout_url, order_no}
        """
        ...

    def handle_payment_success(self, order_no: str) -> None:
        """Called by webhook: activate subscription or add credits."""
        ...

    def get_subscription(self, user_id: int) -> Dict[str, Any]:
        """Get current subscription status."""
        ...

    def cancel_subscription(self, user_id: int) -> bool:
        """Cancel auto-renewal (subscription continues until expire_at)."""
        ...

    def check_and_expire(self) -> int:
        """Cron job: expire overdue subscriptions. Returns count expired."""
        ...
```

---

## 5. 支付 API

#### [NEW] `api/v1/endpoints/payment.py`

```python
router = APIRouter(prefix="/payment", tags=["payment"])

@router.post("/checkout")
async def create_checkout(request: Request, body: CheckoutRequest): ...

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request): ...

@router.post("/webhook/wechat")
async def wechat_webhook(request: Request): ...  # Stub

@router.get("/orders")
async def list_orders(request: Request): ...

@router.get("/subscription")
async def get_subscription(request: Request): ...
```

---

## 6. 前端

### 6.1 定价页

#### [NEW] `apps/dsa-web/src/pages/PricingPage.tsx`

三档展示 + 购买按钮 → 跳转 Stripe Checkout → 返回成功页。

### 6.2 用户面板订阅状态

#### [MODIFY] `apps/dsa-web/src/pages/SettingsPage.tsx`

订阅状态卡片：当前等级、到期时间、升级按钮。

---

## 7. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| NEW | `src/payment/base.py` | 支付抽象接口 |
| NEW | `src/payment/stripe_provider.py` | Stripe 适配器 |
| NEW | `src/payment/wechat_provider.py` | 微信支付桩 |
| NEW | `src/payment/alipay_provider.py` | 支付宝桩 |
| NEW | `src/services/subscription_service.py` | 订阅服务 |
| NEW | `api/v1/endpoints/payment.py` | 支付 API |
| NEW | `api/middlewares/quota.py` | 配额中间件 |
| NEW | `apps/dsa-web/src/pages/PricingPage.tsx` | 定价页 |
| MODIFY | `src/models/user.py` | PaymentOrder / UsageRecord 模型 |
| MODIFY | `apps/dsa-web/src/pages/SettingsPage.tsx` | 订阅状态卡片 |
| MODIFY | `apps/dsa-web/src/App.tsx` | 新增 /pricing 路由 |
| MODIFY | `.env.example` | STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET |
| MODIFY | `requirements.txt` | 新增 stripe |

---

## 8. 验收标准

- [ ] 三档订阅配额正确执行（自选股上限、Agent 次数限制、功能门控）
- [ ] 免费 7 天到期后自动分析停止
- [ ] Stripe Checkout 流程完整：创建→支付→Webhook→激活订阅
- [ ] 临时分析购买：扣减 credits，可用
- [ ] 微信/支付宝 Provider 桩不影响运行
