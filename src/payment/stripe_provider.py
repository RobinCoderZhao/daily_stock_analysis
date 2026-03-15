# -*- coding: utf-8 -*-
"""Stripe Checkout integration.

Handles:
- Creating Checkout Sessions for one-time payments
- Verifying webhook signatures
- Processing refunds

Requires: pip install stripe
Config: STRIPE_SECRET_KEY + STRIPE_WEBHOOK_SECRET in env
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.payment.base import PaymentProvider, CheckoutResult, WebhookEvent, RefundResult

logger = logging.getLogger(__name__)

# Plan display names
PLAN_NAMES = {
    "standard_monthly": "标准会员 - 月度",
    "standard_yearly": "标准会员 - 年度",
    "pro_monthly": "专业会员 - 月度",
    "pro_yearly": "专业会员 - 年度",
    "temp_10": "分析次数 x10",
    "temp_50": "分析次数 x50",
    "temp_100": "分析次数 x100",
}


def _get_base_url() -> str:
    host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    port = os.environ.get("WEBUI_PORT", "8000")
    return os.environ.get("SITE_BASE_URL", f"http://{host}:{port}")


class StripeProvider(PaymentProvider):
    """Stripe Checkout payment provider."""

    def __init__(self):
        self._api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self._webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not self._api_key:
            logger.warning("STRIPE_SECRET_KEY not set — Stripe payments disabled")

    def _get_stripe(self):
        """Lazy import stripe to avoid hard dependency."""
        try:
            import stripe
            stripe.api_key = self._api_key
            return stripe
        except ImportError:
            raise RuntimeError(
                "stripe package not installed. Install with: pip install stripe"
            )

    async def create_checkout(self, order: Any) -> CheckoutResult:
        """Create a Stripe Checkout Session."""
        stripe = self._get_stripe()

        plan_name = PLAN_NAMES.get(order.plan, order.plan)
        base_url = _get_base_url()

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": order.currency.lower(),
                    "product_data": {"name": plan_name},
                    "unit_amount": order.amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            metadata={"order_no": order.order_no},
            success_url=f"{base_url}/payment/success?order={order.order_no}",
            cancel_url=f"{base_url}/payment/cancel",
        )

        return CheckoutResult(
            checkout_url=session.url,
            provider_session_id=session.id,
        )

    async def verify_webhook(self, payload: bytes, headers: dict) -> WebhookEvent:
        """Verify Stripe webhook signature and parse event."""
        stripe = self._get_stripe()

        sig = headers.get("stripe-signature", "")
        event = stripe.Webhook.construct_event(
            payload, sig, self._webhook_secret
        )

        session = event["data"]["object"]
        return WebhookEvent(
            event_type=event["type"],
            order_no=session.get("metadata", {}).get("order_no", ""),
            amount_cents=session.get("amount_total", 0),
            provider_data=dict(session),
        )

    async def refund(self, order_no: str, amount_cents: int) -> RefundResult:
        """Issue a Stripe refund (placeholder — needs payment_intent lookup)."""
        logger.warning(f"Stripe refund not fully implemented for order {order_no}")
        return RefundResult(success=False, error="Refund not yet implemented")
