# -*- coding: utf-8 -*-
"""Signal and strategy backtest API endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.signals import (
    SignalCreateRequest,
    SignalCreateResponse,
    SignalItem,
    SignalSummary,
    SignalsResponse,
    StrategyBacktestRunRequest,
    StrategyBacktestRunResponse,
    StrategyPerformanceItem,
    StrategyRankingResponse,
)
from src.services.signal_service import SignalService
from src.services.strategy_backtest_service import StrategyBacktestService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Signal endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=SignalsResponse,
    summary="Get signals list",
    description="Paginated list of trading signals with optional status/code filters",
)
def get_signals(
    status: Optional[str] = Query(None, description="Filter by status"),
    code: Optional[str] = Query(None, description="Filter by stock code"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> SignalsResponse:
    try:
        service = SignalService(db_manager)
        data = service.get_all_signals(status=status, code=code, page=page, limit=limit)
        items = [SignalItem(**item) for item in data.get("items", [])]
        return SignalsResponse(
            total=data.get("total", 0),
            page=page,
            limit=limit,
            items=items,
        )
    except Exception as exc:
        logger.error("Failed to get signals: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/summary",
    response_model=SignalSummary,
    summary="Get signal performance summary",
)
def get_signal_summary(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> SignalSummary:
    try:
        service = SignalService(db_manager)
        data = service.get_signal_summary()
        return SignalSummary(**data)
    except Exception as exc:
        logger.error("Failed to get signal summary: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/{signal_id}",
    response_model=SignalItem,
    summary="Get signal detail",
    responses={404: {"model": ErrorResponse}},
)
def get_signal_detail(
    signal_id: int,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> SignalItem:
    service = SignalService(db_manager)
    data = service.get_signal_by_id(signal_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return SignalItem(**data)


@router.post(
    "/",
    response_model=SignalCreateResponse,
    summary="Create a signal manually",
)
def create_signal(
    request: SignalCreateRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> SignalCreateResponse:
    service = SignalService(db_manager)
    signal_id = service.create_signal_from_report(
        analysis_history_id=0,
        code=request.code,
        stock_name=request.stock_name,
        strategy_name=request.strategy_name,
        direction=request.direction,
        entry_price=request.entry_price,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        position_pct=request.position_pct,
        confidence=request.confidence,
        holding_days=request.holding_days,
    )
    if signal_id is None:
        raise HTTPException(status_code=500, detail="Failed to create signal")
    return SignalCreateResponse(signal_id=signal_id)


@router.post(
    "/{signal_id}/close",
    summary="Manually close a signal",
    responses={404: {"model": ErrorResponse}},
)
def close_signal(
    signal_id: int,
    db_manager: DatabaseManager = Depends(get_database_manager),
):
    service = SignalService(db_manager)
    ok = service.close_signal(signal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Signal not found")
    return {"message": "Signal closed", "signal_id": signal_id}


# ---------------------------------------------------------------------------
# Strategy backtest endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/strategy-ranking",
    response_model=StrategyRankingResponse,
    summary="Get strategy performance ranking",
)
def get_strategy_ranking(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> StrategyRankingResponse:
    try:
        service = StrategyBacktestService(db_manager)
        summaries = service.get_strategy_ranking()
        items = [StrategyPerformanceItem(**s) for s in summaries]
        return StrategyRankingResponse(strategies=items)
    except Exception as exc:
        logger.error("Failed to get strategy ranking: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/strategy-backtest",
    response_model=StrategyBacktestRunResponse,
    summary="Run strategy-level backtest",
    description="Run quantitative backtests for one or all strategies",
)
def run_strategy_backtest(
    request: StrategyBacktestRunRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> StrategyBacktestRunResponse:
    try:
        service = StrategyBacktestService(db_manager)
        result = service.run_strategy_backtest(
            strategy_name=request.strategy_name,
            code=request.code,
            limit_stocks=request.limit_stocks,
            eval_window_days=request.eval_window_days,
        )
        items = [
            StrategyPerformanceItem(**r) for r in result.get("results", [])
        ]
        return StrategyBacktestRunResponse(
            strategies_tested=result.get("strategies_tested", 0),
            results=items,
            error=result.get("error"),
        )
    except Exception as exc:
        logger.error("Strategy backtest failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
