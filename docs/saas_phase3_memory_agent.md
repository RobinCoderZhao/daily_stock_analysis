# SaaS Phase 3：记忆系统 + Agent 升级

> 本阶段目标：集成 Mem0 记忆存储系统，让 Agent 对话具备跨会话记忆和用户画像能力。
> 前置条件：Phase 2 完成（user_id 隔离可用）
> 预计工期：2 周

---

## 1. Mem0 集成

### 1.1 依赖与配置

#### [MODIFY] `requirements.txt`

```
mem0ai>=0.1.0
```

#### [MODIFY] `.env.example`

```ini
# === Memory System ===
MEMORY_ENABLED=true
MEMORY_LLM_MODEL=gpt-4o-mini
# pgvector extension required on PostgreSQL
```

#### PostgreSQL pgvector 扩展

```sql
-- 在 PostgreSQL 中执行
CREATE EXTENSION IF NOT EXISTS vector;
```

### 1.2 记忆服务层

#### [NEW] `src/services/memory_service.py`

```python
"""User memory management powered by Mem0.

Provides semantic long-term memory for Agent conversations.
Each user has isolated memory space via user_id.
"""

from mem0 import Memory
from typing import Optional, List, Dict, Any

class MemoryService:
    """Manage user-level semantic memory."""

    def __init__(self):
        self._memory = Memory.from_config({
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "connection_string": _get_database_url(),
                    "collection_name": "user_memories",
                }
            },
            "llm": {
                "provider": "litellm",
                "config": {"model": _get_memory_llm_model()}
            },
        })

    def add_conversation(
        self,
        user_id: int,
        messages: List[Dict[str, str]],
        session_id: str = None,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict]:
        """Add conversation to user's memory.

        Mem0 will auto-extract key facts, preferences, etc.
        Example: "用户关注新能源板块", "偏好成长股"
        """
        return self._memory.add(
            messages=messages,
            user_id=str(user_id),
            metadata={**(metadata or {}), "session_id": session_id},
        )

    def search(
        self,
        user_id: int,
        query: str,
        limit: int = 10,
    ) -> List[Dict]:
        """Semantic search user's memories."""
        return self._memory.search(
            query=query,
            user_id=str(user_id),
            limit=limit,
        )

    def get_all(self, user_id: int) -> List[Dict]:
        """Get all memories for a user (for profile display)."""
        return self._memory.get_all(user_id=str(user_id))

    def delete_memory(self, memory_id: str) -> None:
        """Delete a specific memory entry."""
        self._memory.delete(memory_id)

    def clear_user_memories(self, user_id: int) -> None:
        """Clear all memories for a user (account deletion / privacy)."""
        self._memory.delete_all(user_id=str(user_id))
```

---

## 2. Agent 对话记忆注入

### 2.1 对话流程改造

#### [MODIFY] `api/v1/endpoints/agent.py`

在 Agent 对话时注入用户历史记忆：

```python
@router.post("/chat")
async def agent_chat(request: Request, body: ChatRequest):
    user_id = request.state.user_id

    # 1. Retrieve relevant memories
    memory_service = MemoryService()
    memories = memory_service.search(user_id, body.message, limit=5)
    memory_context = _format_memories(memories)

    # 2. Build system prompt with memory context
    system_prompt = _build_system_prompt(
        base_prompt=AGENT_SYSTEM_PROMPT,
        user_memories=memory_context,
        user_watchlist=_get_user_watchlist(user_id),
    )

    # 3. Call LLM with memory-augmented context
    response = await _call_agent(system_prompt, body.message, ...)

    # 4. Save conversation to memory (async, non-blocking)
    asyncio.create_task(_save_to_memory(
        memory_service, user_id,
        messages=[
            {"role": "user", "content": body.message},
            {"role": "assistant", "content": response.content},
        ],
        session_id=body.session_id,
    ))

    return response
```

### 2.2 记忆格式化

```python
def _format_memories(memories: List[Dict]) -> str:
    """Format memories into system prompt context block."""
    if not memories:
        return ""
    lines = ["用户历史偏好和关注（来自记忆系统）："]
    for m in memories:
        lines.append(f"- {m['memory']}")
    return "\n".join(lines)
```

---

## 3. 用户投资画像

### 3.1 画像 API

#### [NEW] `api/v1/endpoints/profile.py`

```python
@router.get("/memories")
async def get_user_memories(request: Request):
    """Get user's extracted memory/preference list."""
    ...

@router.get("/investment-profile")
async def get_investment_profile(request: Request):
    """Get auto-generated investment profile tags.

    Returns: preferred sectors, risk tolerance, trading style, etc.
    """
    ...
```

---

## 4. 测试计划

#### [NEW] `tests/test_memory_service.py`

- 添加对话 → 自动提取关键信息
- 语义搜索 → 返回相关记忆
- 用户隔离 → 不同 user_id 记忆独立
- 清除记忆 → 验证隐私删除

---

## 5. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| NEW | `src/services/memory_service.py` | Mem0 记忆服务 |
| NEW | `api/v1/endpoints/profile.py` | 画像/记忆 API |
| NEW | `tests/test_memory_service.py` | 记忆服务测试 |
| MODIFY | `requirements.txt` | 新增 mem0ai |
| MODIFY | `.env.example` | 新增 MEMORY_ENABLED / MEMORY_LLM_MODEL |
| MODIFY | `api/v1/endpoints/agent.py` | 记忆注入对话流程 |
| MODIFY | `src/config.py` | 新增 memory 配置字段 |

---

## 6. 验收标准

- [ ] Mem0 正常读写 pgvector，记忆提取工作
- [ ] Agent 对话自动召回用户历史偏好
- [ ] 不同用户的记忆完全隔离
- [ ] 用户可查看/删除自己的记忆
- [ ] `MEMORY_ENABLED=false` 时跳过记忆逻辑
