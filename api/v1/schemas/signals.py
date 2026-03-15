# -*- coding: utf-8 -*-
"""Pydantic schemas for signal and strategy backtest API endpoints."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class SignalItem(BaseModel):
    """Single signal record."""

    id: int
    analysis_history_id: Optional[int] = None
    code: str
    stock_name: Optional[str] = None
    strategy_name: Optional[str] = None
    direction: str = "long"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_pct: Optional[float] = None
    confidence: Optional[float] = None
    status: str = "pending"
    created_at: Optional[str] = None
    closed_at: Optional[str] = None
    current_price: Optional[float] = None
    return_pct: Optional[float] = None
    holding_days: Optional[int] = None
    expire_date: Optional[str] = None


class SignalsResponse(BaseModel):
    """Paginated signals list."""

    total: int = 0
    page: int = 1
    limit: int = 20
    items: List[SignalItem] = Field(default_factory=list)


class SignalSummary(BaseModel):
    """Aggregated signal performance."""

    total_signals: int = 0
    active_count: int = 0
    closed_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate_pct: Optional[float] = None
    avg_return_pct: Optional[float] = None


class SignalCreateRequest(BaseModel):
    """Request to create a signal manually."""

    code: str
    stock_name: str = ""
    strategy_name: str = ""
    direction: str = "long"
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_pct: Optional[float] = None
    confidence: Optional[float] = None
    holding_days: int = 10


class SignalCreateResponse(BaseModel):
    """Response after creating a signal."""

    signal_id: int
    message: str = "Signal created"


# ---------------------------------------------------------------------------
# Strategy backtest
# ---------------------------------------------------------------------------

class StrategyPerformanceItem(BaseModel):
    """Summary metrics for a single strategy."""

    strategy_name: str
    total_signals: int = 0
    win_count: int = 0
    loss_count: int = 0
    neutral_count: int = 0
    win_rate_pct: Optional[float] = None
    avg_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    avg_holding_days: Optional[float] = None
    stop_loss_trigger_rate: Optional[float] = None
    take_profit_trigger_rate: Optional[float] = None
    computed_confidence: Optional[float] = None
    computed_at: Optional[str] = None


class StrategyRankingResponse(BaseModel):
    """All strategies ranked by performance."""

    strategies: List[StrategyPerformanceItem] = Field(default_factory=list)


class StrategyBacktestRunRequest(BaseModel):
    """Request to run a strategy backtest."""

    strategy_name: Optional[str] = None
    code: Optional[str] = None
    limit_stocks: int = Field(default=50, ge=1, le=200)
    eval_window_days: int = Field(default=10, ge=1, le=120)


class StrategyBacktestRunResponse(BaseModel):
    """Response after running strategy backtests."""

    strategies_tested: int = 0
    results: List[StrategyPerformanceItem] = Field(default_factory=list)
    error: Optional[str] = None
