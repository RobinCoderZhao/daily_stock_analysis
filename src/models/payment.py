# -*- coding: utf-8 -*-
"""Payment and usage data models for subscription billing."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Index
from src.storage import Base


class PaymentOrder(Base):
    """Payment order record."""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)
    plan = Column(String(32), nullable=False)
    # plan: standard_monthly / pro_monthly / standard_yearly / pro_yearly
    #       temp_10 / temp_50 / temp_100
    amount_cents = Column(Integer, nullable=False)  # Amount in cents
    currency = Column(String(8), nullable=False, default="CNY")
    payment_provider = Column(String(32), nullable=True)  # stripe / wechat / alipay
    payment_provider_id = Column(String(255), nullable=True)  # Stripe session ID etc.
    status = Column(String(20), nullable=False, default="pending")
    # status: pending / paid / refunded / failed / expired
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "order_no": self.order_no,
            "plan": self.plan,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "payment_provider": self.payment_provider,
            "status": self.status,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UsageRecord(Base):
    """Per-action usage tracking for billing and analytics."""
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(32), nullable=False)
    # action: analysis / agent_chat / backtest / temp_analysis
    stock_code = Column(String(16), nullable=True)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_usage_user_date", "user_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "stock_code": self.stock_code,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
