# -*- coding: utf-8 -*-
"""Admin platform API key management endpoints.

Requires super_admin role.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.middlewares.admin import super_admin_required

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/keys",
    tags=["admin"],
    dependencies=[Depends(super_admin_required)],
)


class AddKeyRequest(BaseModel):
    provider: str
    raw_key: str
    priority: int = 0
    daily_limit: Optional[int] = None
    label: str = ""


@router.get("/")
async def list_keys(provider: Optional[str] = None):
    """List platform API keys (masked values)."""
    from src.services.platform_key_service import PlatformKeyService
    service = PlatformKeyService()
    return {"keys": service.list_keys(provider)}


@router.post("/")
async def add_key(body: AddKeyRequest):
    """Add a new encrypted platform API key."""
    from src.services.platform_key_service import PlatformKeyService
    service = PlatformKeyService()
    key_id = service.add_key(
        provider=body.provider,
        raw_key=body.raw_key,
        priority=body.priority,
        daily_limit=body.daily_limit,
        label=body.label,
    )
    return {"ok": True, "key_id": key_id}


@router.put("/{key_id}/deactivate")
async def deactivate_key(key_id: int):
    """Deactivate a platform API key."""
    from src.services.platform_key_service import PlatformKeyService
    service = PlatformKeyService()
    success = service.deactivate_key(key_id)
    if success:
        return {"ok": True}
    return JSONResponse(404, {"error": "key_not_found"})


@router.get("/usage")
async def key_usage_stats():
    """Get platform API key usage statistics by provider."""
    from src.services.platform_key_service import PlatformKeyService
    service = PlatformKeyService()
    return {"stats": service.get_usage_stats()}
