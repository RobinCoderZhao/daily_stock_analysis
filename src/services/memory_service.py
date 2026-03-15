# -*- coding: utf-8 -*-
"""User memory management powered by Mem0.

Provides semantic long-term memory for Agent conversations.
Each user has isolated memory space via user_id.

When MEMORY_ENABLED=false (default), all methods are no-ops.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_memory_instance = None


def _get_database_url() -> str:
    """Get PostgreSQL connection string for pgvector."""
    return os.environ.get("DATABASE_URL", "")


def _get_memory_llm_model() -> str:
    """Get LLM model for memory extraction."""
    return os.environ.get("MEMORY_LLM_MODEL", "gpt-4o-mini")


def _is_memory_enabled() -> bool:
    return os.environ.get("MEMORY_ENABLED", "").lower() in ("true", "1", "yes")


class MemoryService:
    """Manage user-level semantic memory via Mem0.

    Thread-safe singleton for the Mem0 Memory instance.
    Falls back to no-op when MEMORY_ENABLED=false or mem0 not installed.
    """

    def __init__(self):
        self._memory = None
        self._available = False

        if not _is_memory_enabled():
            logger.debug("Memory system disabled (MEMORY_ENABLED is not true)")
            return

        try:
            self._memory = self._create_memory()
            self._available = True
            logger.info("Mem0 memory service initialized")
        except ImportError:
            logger.warning(
                "mem0ai not installed. Memory features disabled. "
                "Install with: pip install mem0ai"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Mem0: {e}. Memory features disabled.")

    def _create_memory(self):
        """Create Mem0 Memory instance with pgvector backend."""
        from mem0 import Memory

        db_url = _get_database_url()
        config: Dict[str, Any] = {
            "llm": {
                "provider": "litellm",
                "config": {"model": _get_memory_llm_model()},
            },
        }

        # Use pgvector if DATABASE_URL is a PostgreSQL URL
        if db_url and db_url.startswith("postgresql"):
            config["vector_store"] = {
                "provider": "pgvector",
                "config": {
                    "connection_string": db_url,
                    "collection_name": "user_memories",
                },
            }

        return Memory.from_config(config)

    @property
    def available(self) -> bool:
        """Whether memory system is active."""
        return self._available

    def add_conversation(
        self,
        user_id: int,
        messages: List[Dict[str, str]],
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """Add conversation to user's memory.

        Mem0 auto-extracts key facts, preferences, etc.
        Example: "user focuses on new energy sector", "prefers growth stocks"
        """
        if not self._available:
            return []

        try:
            extra = {**(metadata or {})}
            if session_id:
                extra["session_id"] = session_id

            result = self._memory.add(
                messages=messages,
                user_id=str(user_id),
                metadata=extra if extra else None,
            )
            logger.debug(f"Added {len(result) if result else 0} memories for user {user_id}")
            return result or []
        except Exception as e:
            logger.error(f"Memory add failed for user {user_id}: {e}")
            return []

    def search(
        self,
        user_id: int,
        query: str,
        limit: int = 10,
    ) -> List[Dict]:
        """Semantic search user's memories."""
        if not self._available:
            return []

        try:
            return self._memory.search(
                query=query,
                user_id=str(user_id),
                limit=limit,
            ) or []
        except Exception as e:
            logger.error(f"Memory search failed for user {user_id}: {e}")
            return []

    def get_all(self, user_id: int) -> List[Dict]:
        """Get all memories for a user (for profile display)."""
        if not self._available:
            return []

        try:
            return self._memory.get_all(user_id=str(user_id)) or []
        except Exception as e:
            logger.error(f"Memory get_all failed for user {user_id}: {e}")
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory entry."""
        if not self._available:
            return False

        try:
            self._memory.delete(memory_id)
            return True
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return False

    def clear_user_memories(self, user_id: int) -> bool:
        """Clear all memories for a user (account deletion / privacy)."""
        if not self._available:
            return False

        try:
            self._memory.delete_all(user_id=str(user_id))
            logger.info(f"Cleared all memories for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Memory clear failed for user {user_id}: {e}")
            return False


def format_memories_for_prompt(memories: List[Dict]) -> str:
    """Format memories into system prompt context block.

    Returns empty string if no memories, otherwise a formatted block
    that can be appended to the system prompt.
    """
    if not memories:
        return ""

    lines = ["用户历史偏好和关注（来自记忆系统）："]
    for m in memories:
        text = m.get("memory") or m.get("text") or str(m)
        lines.append(f"- {text}")
    return "\n".join(lines)
