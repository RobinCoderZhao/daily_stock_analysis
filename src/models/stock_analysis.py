# -*- coding: utf-8 -*-
"""Stock-centric analysis deduplication model.

When SAAS_MODE is active, each stock is analyzed at most once per day.
The result is shared across all users who have this stock in their watchlists.
"""

from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, DateTime, Date, ForeignKey,
    UniqueConstraint, Index,
)
from src.storage import Base


class StockAnalysisDaily(Base):
    """Global per-stock per-day analysis state.

    Status lifecycle: pending → analyzing → completed / failed

    When a scheduled analysis runs:
    1. Insert row with status='pending' (or find existing)
    2. CAS update status to 'analyzing' (prevents double-work)
    3. Run LLM analysis
    4. Update status to 'completed', set result_id
    5. On error: set status='failed' with error_message

    Users query their watchlist stocks and join to this table
    to get the latest shared analysis result.
    """
    __tablename__ = "stock_analysis_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False)
    analysis_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    # status: pending / analyzing / completed / failed
    result_id = Column(Integer, nullable=True)
    # FK to analysis_history.id (not enforced at DB level for cross-DB compat)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(String(500), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("code", "analysis_date", name="uix_stock_analysis_daily"),
        Index("ix_sad_date_status", "analysis_date", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
            "status": self.status,
            "result_id": self.result_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }
