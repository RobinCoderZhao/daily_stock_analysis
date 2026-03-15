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
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    items = service.get_watchlist(user_id, group=group)
    return {"items": items, "count": len(items)}


@router.post("/add")
async def add_stock(request: Request, body: AddStockRequest):
    """Add stock to watchlist."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

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
        return JSONResponse(status, {"error": e.code, "message": str(e)})


@router.delete("/{code}")
async def remove_stock(request: Request, code: str):
    """Remove stock from watchlist."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService, WatchlistServiceError
    try:
        service = WatchlistService()
        service.remove_stock(user_id, code)
        return {"ok": True}
    except WatchlistServiceError as e:
        return JSONResponse(404, {"error": e.code, "message": str(e)})


@router.get("/groups")
async def get_groups(request: Request):
    """Get user's watchlist group names."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    groups = service.get_groups(user_id)
    return {"groups": groups}


@router.put("/reorder")
async def reorder(request: Request, body: ReorderRequest):
    """Update sort order for stocks."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    service.reorder(user_id, body.code_order)
    return {"ok": True}


@router.get("/quota")
async def get_quota(request: Request):
    """Get user's watchlist quota info."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.watchlist_service import WatchlistService
    service = WatchlistService()
    return service.get_quota_info(user_id)
