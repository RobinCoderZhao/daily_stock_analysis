# -*- coding: utf-8 -*-
"""Watchlist API endpoints for SaaS mode."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class AddStockRequest(BaseModel):
    code: str
    name: Optional[str] = None
    group: str = "默认分组"
    market: str = "cn"


class ReorderRequest(BaseModel):
    code_order: List[str]


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _get_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise ValueError("not_authenticated")
    return user_id


@router.get("/")
async def get_watchlist(request: Request, group: Optional[str] = None):
    """Get user's watchlist."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    items = service.get_watchlist(user_id, group=group)
    return {"items": items, "count": len(items)}


@router.post("/add")
async def add_stock(request: Request, body: AddStockRequest):
    """Add stock to watchlist."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService, WatchlistServiceError
    try:
        service = WatchlistService()
        result = service.add_stock(
            user_id=user_id,
            code=body.code,
            name=body.name,
            group=body.group,
            market=body.market,
        )
        return result
    except WatchlistServiceError as e:
        status = 409 if e.code == "already_exists" else 400
        if e.code == "quota_exceeded":
            status = 403
        return JSONResponse(status_code=status, content={"error": e.code, "message": str(e)})


@router.delete("/{code}")
async def remove_stock(request: Request, code: str):
    """Remove stock from watchlist."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService, WatchlistServiceError
    try:
        service = WatchlistService()
        service.remove_stock(user_id, code)
        return {"ok": True}
    except WatchlistServiceError as e:
        return JSONResponse(status_code=404, content={"error": e.code, "message": str(e)})


@router.get("/groups")
async def get_groups(request: Request):
    """Get user's watchlist group names."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    groups = service.get_groups(user_id)
    return {"groups": groups}


@router.put("/reorder")
async def reorder(request: Request, body: ReorderRequest):
    """Update sort order for stocks."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    service.reorder(user_id, body.code_order)
    return {"ok": True}


@router.get("/quota")
async def get_quota(request: Request):
    """Get user's watchlist quota info."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    return service.get_quota_info(user_id)


@router.get("/enriched")
async def get_enriched_watchlist(request: Request):
    """Get watchlist enriched with latest analysis scores and stock info."""
    if not _is_saas_mode():
        return JSONResponse(status_code=400, content={"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(status_code=401, content={"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    items = service.get_watchlist(user_id)

    if not items:
        return {"items": [], "count": 0}

    # Enrich each item with latest analysis data from global analysis_history
    from src.storage import DatabaseManager
    db = DatabaseManager.get_instance()
    enriched = []
    for item in items:
        code = item["code"]
        # Get the most recent analysis for this stock (global, not per-user)
        records = db.get_analysis_history(code=code, days=90, limit=1)
        latest = records[0] if records else None

        enriched.append({
            "id": item["id"],
            "code": code,
            "name": item.get("name") or (latest.name if latest else code),
            "group": item.get("group", "默认分组"),
            "market": item.get("market", "cn"),
            "sort_order": item.get("sort_order", 0),
            "added_at": item.get("added_at"),
            # Analysis data (from most recent analysis)
            "analysis_id": latest.id if latest else None,
            "sentiment_score": latest.sentiment_score if latest else None,
            "composite_score": latest.composite_score if latest else None,
            "composite_label": latest.composite_label if latest else None,
            "operation_advice": latest.operation_advice if latest else None,
            "analysis_summary": latest.analysis_summary if latest else None,
            "analysis_date": latest.created_at.isoformat() if latest and latest.created_at else None,
            "query_id": latest.query_id if latest else None,
            # Score breakdown
            "technical_score": latest.technical_score if latest else None,
            "fundamental_score": latest.fundamental_score if latest else None,
            "money_flow_score": latest.money_flow_score if latest else None,
            "market_score": latest.market_score if latest else None,
            "confidence_score": latest.confidence_score if latest else None,
            "trend_prediction": latest.trend_prediction if latest else None,
        })

    return {"items": enriched, "count": len(enriched)}
