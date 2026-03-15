# -*- coding: utf-8 -*-
"""WeChat Pay provider stub.

To be implemented when business license and WeChat Pay merchant account are ready.
"""

from __future__ import annotations

from src.payment.base import PaymentProvider, CheckoutResult, WebhookEvent, RefundResult


class WechatPayProvider(PaymentProvider):
    """WeChat Pay stub — raises NotImplementedError for all methods."""

    async def create_checkout(self, order) -> CheckoutResult:
        raise NotImplementedError("WeChat Pay not configured — business license required")

    async def verify_webhook(self, payload: bytes, headers: dict) -> WebhookEvent:
        raise NotImplementedError("WeChat Pay not configured")

    async def refund(self, order_no: str, amount_cents: int) -> RefundResult:
        raise NotImplementedError("WeChat Pay not configured")
