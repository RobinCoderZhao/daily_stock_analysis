# -*- coding: utf-8 -*-
"""User profile and memory API endpoints (SaaS mode)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


def _is_saas_mode() -> bool:
    return os.environ.get("SAAS_MODE", "").lower() in ("true", "1", "yes")


def _get_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise ValueError("not_authenticated")
    return user_id


@router.get("/memories")
async def get_user_memories(request: Request):
    """Get user's extracted memory/preference list."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.memory_service import MemoryService
    service = MemoryService()
    if not service.available:
        return {"memories": [], "message": "Memory system not enabled"}

    memories = service.get_all(user_id)
    return {
        "memories": memories,
        "count": len(memories),
    }


class DeleteMemoryRequest(BaseModel):
    memory_id: str


@router.delete("/memories/{memory_id}")
async def delete_memory(request: Request, memory_id: str):
    """Delete a specific memory entry."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.memory_service import MemoryService
    service = MemoryService()
    if not service.available:
        return JSONResponse(400, {"error": "memory_disabled"})

    success = service.delete_memory(memory_id)
    if success:
        return {"ok": True}
    return JSONResponse(500, {"error": "delete_failed"})


@router.delete("/memories")
async def clear_all_memories(request: Request):
    """Clear all memories for the current user (privacy)."""
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.memory_service import MemoryService
    service = MemoryService()
    if not service.available:
        return JSONResponse(400, {"error": "memory_disabled"})

    success = service.clear_user_memories(user_id)
    if success:
        return {"ok": True}
    return JSONResponse(500, {"error": "clear_failed"})


@router.get("/investment-profile")
async def get_investment_profile(request: Request):
    """Get auto-generated investment profile from memories.

    Returns: preferred sectors, risk tolerance, trading style, etc.
    """
    if not _is_saas_mode():
        return JSONResponse(400, {"error": "saas_only"})

    try:
        user_id = _get_user_id(request)
    except ValueError:
        return JSONResponse(401, {"error": "not_authenticated"})

    from src.services.memory_service import MemoryService
    service = MemoryService()
    if not service.available:
        return {
            "profile": {},
            "message": "Memory system not enabled. No profile available.",
        }

    # Search for investment-related memories
    memories = service.get_all(user_id)

    # Auto-categorize memories into profile tags
    profile = _extract_investment_profile(memories)

    return {
        "profile": profile,
        "memory_count": len(memories),
    }


def _extract_investment_profile(memories: list) -> dict:
    """Extract investment profile tags from raw memories.

    Categories: sectors, risk_level, style, focus_stocks
    """
    profile = {
        "sectors": [],
        "risk_level": "unknown",
        "style": "unknown",
        "focus_areas": [],
        "summary": "",
    }

    if not memories:
        return profile

    # Simple keyword-based extraction (can be enhanced with LLM later)
    all_text = " ".join(
        m.get("memory", "") or m.get("text", "") or ""
        for m in memories
    ).lower()

    # Sector detection
    sector_keywords = {
        "新能源": "新能源", "光伏": "新能源", "锂电": "新能源",
        "半导体": "半导体/芯片", "芯片": "半导体/芯片",
        "消费": "消费", "白酒": "消费", "食品": "消费",
        "医药": "医药/生物", "生物": "医药/生物",
        "银行": "金融", "券商": "金融", "保险": "金融",
        "地产": "地产", "房地产": "地产",
        "军工": "国防军工",
        "人工智能": "AI/科技", "ai": "AI/科技",
    }
    for keyword, sector in sector_keywords.items():
        if keyword in all_text and sector not in profile["sectors"]:
            profile["sectors"].append(sector)

    # Style detection
    if any(w in all_text for w in ["短线", "day trade", "打板", "追涨"]):
        profile["style"] = "短线交易"
    elif any(w in all_text for w in ["长线", "价值投资", "长期持有"]):
        profile["style"] = "价值投资"
    elif any(w in all_text for w in ["成长", "高增长"]):
        profile["style"] = "成长投资"

    # Risk detection
    if any(w in all_text for w in ["保守", "稳健", "低风险"]):
        profile["risk_level"] = "保守"
    elif any(w in all_text for w in ["激进", "高风险", "杠杆"]):
        profile["risk_level"] = "激进"

    profile["summary"] = f"关注 {len(profile['sectors'])} 个板块，{profile['style']}风格"
    return profile
