# -*- coding: utf-8 -*-
"""PlatformApiKey model for encrypted API key storage."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text
from src.storage import Base


class PlatformApiKey(Base):
    """Encrypted platform API key (LLM, search, etc.)."""
    __tablename__ = "platform_api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(32), nullable=False, index=True)
    # e.g.: gemini, openai, deepseek, anthropic, tavily, bocha
    encrypted_key = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher = used first
    daily_limit = Column(Integer, nullable=True)  # None = unlimited
    used_today = Column(Integer, default=0)
    label = Column(String(100), nullable=True)  # Human-readable label
    last_rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self, mask_key: bool = True):
        return {
            "id": self.id,
            "provider": self.provider,
            "key_preview": self._mask_key() if mask_key else None,
            "is_active": self.is_active,
            "priority": self.priority,
            "daily_limit": self.daily_limit,
            "used_today": self.used_today,
            "label": self.label,
            "last_rotated_at": (
                self.last_rotated_at.isoformat() if self.last_rotated_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _mask_key(self) -> str:
        """Return masked key preview (first 4 + last 4 chars)."""
        # encrypted_key is the encrypted value, not usable for preview
        return "****"
