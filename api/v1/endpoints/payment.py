# -*- coding: utf-8 -*-
"""Payment and subscription API endpoints."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment", tags=["payment"])


class CheckoutRequest(BaseModel):
    plan: str  # standard_monthly / pro_monthly / temp_10 etc.


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _get_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise ValueError("not_authenticated")
    return user_id


@router.get("/plans")
async def get_plans():
    """Get available subscription plans and pricing."""
    from src.services.subscription_service import SubscriptionService
    service = SubscriptionService()
    return service.get_plans()


@router.post("/checkout")
async def create_checkout(request: Request, body: CheckoutRequest):
    """Create a payment checkout session."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.subscription_service import SubscriptionService, SubscriptionServiceError
    try:
        service = SubscriptionService()
        order_info = service.create_checkout(user_id, body.plan)

        # Try to create Stripe checkout session
        provider = os.environ.get("PAYMENT_PROVIDER", "stripe")
        if provider == "stripe" and os.environ.get("STRIPE_SECRET_KEY"):
            try:
                from src.payment.stripe_provider import StripeProvider
                from src.models.payment import PaymentOrder
                from src.storage import DatabaseManager

                db = DatabaseManager.get_instance()
                with db.get_session() as session:
                    order = (
                        session.query(PaymentOrder)
                        .filter_by(order_no=order_info["order_no"])
                        .first()
                    )

                stripe_provider = StripeProvider()
                import asyncio
                result = await stripe_provider.create_checkout(order)

                # Update order with provider ID
                with db.get_session() as session:
                    order = (
                        session.query(PaymentOrder)
                        .filter_by(order_no=order_info["order_no"])
                        .first()
                    )
                    if order:
                        order.payment_provider = "stripe"
                        order.payment_provider_id = result.provider_session_id
                        session.commit()

                order_info["checkout_url"] = result.checkout_url
            except Exception as e:
                logger.error(f"Stripe checkout failed: {e}")
                order_info["checkout_url"] = None
                order_info["error"] = "payment_provider_error"
        else:
            order_info["checkout_url"] = None

        return order_info

    except SubscriptionServiceError as e:
        return JSONResponse(400, {"error": e.code, "message": str(e)})


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook callbacks."""
    payload = await request.body()
    headers = dict(request.headers)

    try:
        from src.payment.stripe_provider import StripeProvider
        provider = StripeProvider()
        event = await provider.verify_webhook(payload, headers)

        if event.event_type == "checkout.session.completed":
            from src.services.subscription_service import SubscriptionService
            service = SubscriptionService()
            service.handle_payment_success(
                order_no=event.order_no,
                provider="stripe",
                provider_id=str(event.provider_data.get("id", "")),
            )

        return {"ok": True}
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return JSONResponse(400, {"error": "webhook_error", "message": str(e)})


@router.post("/webhook/wechat")
async def wechat_webhook(request: Request):
    """Handle WeChat Pay webhook (stub)."""
    return JSONResponse(501, {"error": "not_implemented",
                               "message": "WeChat Pay not yet configured"})


@router.post("/webhook/alipay")
async def alipay_webhook(request: Request):
    """Handle Alipay webhook (stub)."""
    return JSONResponse(501, {"error": "not_implemented",
                               "message": "Alipay not yet configured"})


@router.get("/subscription")
async def get_subscription(request: Request):
    """Get current user's subscription status."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.subscription_service import SubscriptionService
    service = SubscriptionService()
    return service.get_subscription(user_id)


@router.post("/subscription/cancel")
async def cancel_subscription(request: Request):
    """Cancel current subscription."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.subscription_service import SubscriptionService
    service = SubscriptionService()
    success = service.cancel_subscription(user_id)
    if success:
        return {"ok": True}
    return JSONResponse(404, {"error": "no_active_subscription"})


@router.get("/orders")
async def list_orders(request: Request, limit: int = 20):
    """List user's payment orders."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.models.payment import PaymentOrder
    from src.storage import DatabaseManager

    db = DatabaseManager.get_instance()
    with db.get_session() as session:
        orders = (
            session.query(PaymentOrder)
            .filter_by(user_id=user_id)
            .order_by(PaymentOrder.created_at.desc())
            .limit(limit)
            .all()
        )
        return {"orders": [o.to_dict() for o in orders]}
