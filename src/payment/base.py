# -*- coding: utf-8 -*-
"""Payment provider abstract interface.

Defines the contract that all payment providers must implement.
Currently supported: Stripe. Stubs: WeChat Pay, Alipay.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CheckoutResult:
    """Result of creating a checkout session."""
    checkout_url: str
    provider_session_id: str


@dataclass
class WebhookEvent:
    """Parsed webhook event from payment provider."""
    event_type: str       # checkout.completed / payment.refunded
    order_no: str
    amount_cents: int
    provider_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefundResult:
    """Result of a refund operation."""
    success: bool
    refund_id: str = ""
    error: str = ""


class PaymentProvider(ABC):
    """Abstract base for payment providers."""

    @abstractmethod
    async def create_checkout(self, order: Any) -> CheckoutResult:
        """Create a checkout session for the given order."""
        ...

    @abstractmethod
    async def verify_webhook(self, payload: bytes, headers: dict) -> WebhookEvent:
        """Verify and parse a webhook callback."""
        ...

    @abstractmethod
    async def refund(self, order_no: str, amount_cents: int) -> RefundResult:
        """Issue a refund for the given order."""
        ...
