# -*- coding: utf-8 -*-
"""Alipay provider stub.

To be implemented when business license and Alipay merchant account are ready.
"""

from __future__ import annotations

from src.payment.base import PaymentProvider, CheckoutResult, WebhookEvent, RefundResult


class AlipayProvider(PaymentProvider):
    """Alipay stub — raises NotImplementedError for all methods."""

    async def create_checkout(self, order) -> CheckoutResult:
        raise NotImplementedError("Alipay not configured — business license required")

    async def verify_webhook(self, payload: bytes, headers: dict) -> WebhookEvent:
        raise NotImplementedError("Alipay not configured")

    async def refund(self, order_no: str, amount_cents: int) -> RefundResult:
        raise NotImplementedError("Alipay not configured")
