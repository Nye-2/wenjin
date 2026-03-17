# THESIS Workspace Full Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the THESIS workspace from template-based handlers to LangGraph multi-agent architecture with deep LLM generation, context memory system with compaction, and end-to-end feature closure.

**Architecture:** Migrate all 6 THESIS features to LangGraph sub-graphs routed by a ThesisLeadAgent. Add AcademicMemoryMiddleware backed by UserKnowledge DB for cross-session context. Upgrade each feature with multi-step LLM generation pipelines while retaining template fallback.

**Tech Stack:** LangGraph StateGraph, LangChain chat models (existing `create_chat_model()`), deer-flow middleware pattern, PostgreSQL (UserKnowledge), Redis caching (existing)

**Database:** Direct model changes (dev phase, no Alembic migration)

---

## Phase 1: Foundation — LangGraph Engine + Memory System

### Task 1: KnowledgeService CRUD

Create the service layer for UserKnowledge read/write, which all subsequent tasks depend on.

**Files:**
- Create: `src/services/knowledge_service.py`
- Test: `tests/services/test_knowledge_service.py`

**Implementation:**

```python
# src/services/knowledge_service.py
"""CRUD service for UserKnowledge persistence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Manages UserKnowledge lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[UserKnowledge]:
        """Return active knowledge ordered by confidence desc.

        Workspace-specific entries appear first, then global entries.
        """
        stmt = (
            select(UserKnowledge)
            .where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence >= min_confidence,
                )
            )
            .order_by(
                # workspace-specific first
                (UserKnowledge.workspace_context == workspace_context).desc()
                if workspace_context
                else UserKnowledge.confidence.desc(),
                UserKnowledge.confidence.desc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: str,
        category: KnowledgeCategory | str,
        content: str,
        *,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> UserKnowledge:
        """Insert or update (boost confidence if duplicate content)."""
        if isinstance(category, str):
            category = KnowledgeCategory(category)

        # Check for existing similar entry
        stmt = select(UserKnowledge).where(
            and_(
                UserKnowledge.user_id == user_id,
                UserKnowledge.category == category,
                UserKnowledge.content == content,
                UserKnowledge.is_active == True,  # noqa: E712
            )
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.boost_confidence(0.1)
            existing.source = source or existing.source
            await self._db.flush()
            return existing

        entry = UserKnowledge(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def archive_low_confidence(
        self,
        user_id: str,
        threshold: float = 0.5,
    ) -> int:
        """Deactivate entries below threshold. Returns count."""
        stmt = (
            select(UserKnowledge)
            .where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence < threshold,
                )
            )
        )
        result = await self._db.execute(stmt)
        entries = result.scalars().all()
        for entry in entries:
            entry.is_active = False
        await self._db.flush()
        return len(entries)

    async def count_active(self, user_id: str) -> int:
        """Count active knowledge entries for a user."""
        stmt = select(func.count()).select_from(UserKnowledge).where(
            and_(
                UserKnowledge.user_id == user_id,
                UserKnowledge.is_active == True,  # noqa: E712
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()
```

**Tests:**

```python
# tests/services/test_knowledge_service.py
"""Tests for KnowledgeService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge
from src.services.knowledge_service import KnowledgeService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    return KnowledgeService(mock_db)


class TestListActive:
    async def test_returns_list(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        result = await service.list_active("user1")
        assert result == []

    async def test_respects_min_confidence(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        await service.list_active("user1", min_confidence=0.8)
        mock_db.execute.assert_called_once()


class TestUpsert:
    async def test_creates_new_entry(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        entry = await service.upsert(
            "user1",
            KnowledgeCategory.PREFERENCE,
            "Prefers APA",
            confidence=0.9,
            source="test",
        )
        mock_db.add.assert_called_once()
        assert entry.content == "Prefers APA"

    async def test_boosts_existing_confidence(self, service, mock_db):
        existing = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.PREFERENCE,
            content="Prefers APA",
            confidence=0.7,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result
        result = await service.upsert(
            "user1",
            KnowledgeCategory.PREFERENCE,
            "Prefers APA",
        )
        assert result.confidence == pytest.approx(0.8)


class TestArchiveLowConfidence:
    async def test_deactivates_below_threshold(self, service, mock_db):
        entry = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.CONTEXT,
            content="old context",
            confidence=0.3,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entry]
        mock_db.execute.return_value = mock_result
        count = await service.archive_low_confidence("user1", threshold=0.5)
        assert count == 1
        assert entry.is_active is False


class TestCountActive:
    async def test_returns_count(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_db.execute.return_value = mock_result
        count = await service.count_active("user1")
        assert count == 42
```

---

### Task 2: AcademicMemoryMiddleware

Middleware that loads UserKnowledge before agent execution and extracts new knowledge after.

**Files:**
- Create: `src/agents/middleware/__init__.py`
- Create: `src/agents/middleware/memory.py`
- Test: `tests/agents/middleware/test_memory.py`

**Implementation:**

```python
# src/agents/middleware/__init__.py
"""Agent middleware package."""

# src/agents/middleware/memory.py
"""AcademicMemoryMiddleware — loads and persists UserKnowledge."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)

KNOWLEDGE_EXTRACTION_PROMPT = """从以下对话中提取学术相关知识点。返回 JSON 数组:
[
  {
    "category": "preference | knowledge | context | behavior | goal",
    "content": "简洁描述（一句话）",
    "confidence": 0.5-1.0
  }
]

仅提取明确或高度可推断的信息。不要猜测。不确定时不要提取。
category 说明:
- preference: 引用格式偏好、写作风格、语言偏好
- knowledge: 学科知识、专业术语
- context: 当前研究方向、进展状态
- behavior: 操作习惯
- goal: 研究目标、里程碑

对话内容:
{conversation}

仅返回 JSON 数组，不要其他内容。"""


def format_knowledge_for_prompt(knowledge_items: list[dict[str, Any]]) -> str:
    """Format UserKnowledge entries into system prompt injection."""
    if not knowledge_items:
        return ""

    sections: dict[str, list[str]] = {
        "preference": [],
        "knowledge": [],
        "context": [],
        "behavior": [],
        "goal": [],
    }
    for item in knowledge_items:
        cat = item.get("category", "context")
        content = item.get("content", "")
        conf = item.get("confidence", 0.7)
        if cat in sections:
            sections[cat].append(f"- {content} (置信度: {conf:.1f})")

    parts: list[str] = ["<academic_memory>"]
    label_map = {
        "preference": "用户偏好",
        "knowledge": "学科知识",
        "context": "研究上下文",
        "behavior": "行为习惯",
        "goal": "研究目标",
    }
    for cat, label in label_map.items():
        if sections[cat]:
            parts.append(f"\n{label}:")
            parts.extend(sections[cat])
    parts.append("</academic_memory>")
    return "\n".join(parts)


async def load_user_memory(
    user_id: str,
    workspace_id: str | None = None,
    *,
    limit: int = 20,
    min_confidence: float = 0.5,
) -> list[dict[str, Any]]:
    """Load active UserKnowledge from DB."""
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    try:
        async with get_db_session() as db:
            service = KnowledgeService(db)
            entries = await service.list_active(
                user_id,
                workspace_context=workspace_id,
                min_confidence=min_confidence,
                limit=limit,
            )
            return [
                {
                    "category": entry.category.value if hasattr(entry.category, "value") else str(entry.category),
                    "content": entry.content,
                    "confidence": entry.confidence,
                }
                for entry in entries
            ]
    except Exception:
        logger.exception("Failed to load user memory")
        return []


async def extract_and_persist_knowledge(
    user_id: str,
    conversation_text: str,
    *,
    workspace_context: str | None = None,
    source: str | None = None,
) -> int:
    """Extract knowledge from conversation via LLM and persist to DB.

    Returns count of entries persisted.
    """
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.1)
        prompt = KNOWLEDGE_EXTRACTION_PROMPT.format(conversation=conversation_text[:4000])
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON array from response
        items = _parse_knowledge_json(content)
        if not items:
            return 0

        count = 0
        async with get_db_session() as db:
            service = KnowledgeService(db)
            for item in items:
                cat = item.get("category", "")
                text = item.get("content", "")
                conf = float(item.get("confidence", 0.7))
                if not text or conf < 0.5:
                    continue
                try:
                    KnowledgeCategory(cat)  # validate
                except ValueError:
                    continue
                await service.upsert(
                    user_id,
                    cat,
                    text,
                    confidence=conf,
                    source=source,
                    workspace_context=workspace_context,
                )
                count += 1
            await db.commit()
        return count
    except Exception:
        logger.exception("Failed to extract knowledge")
        return 0


def _parse_knowledge_json(text: str) -> list[dict[str, Any]]:
    """Parse JSON array from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return []
```

**Tests:**

```python
# tests/agents/middleware/test_memory.py
"""Tests for AcademicMemoryMiddleware."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.middleware.memory import (
    format_knowledge_for_prompt,
    _parse_knowledge_json,
    load_user_memory,
    extract_and_persist_knowledge,
)


class TestFormatKnowledgeForPrompt:
    def test_empty_returns_empty_string(self):
        assert format_knowledge_for_prompt([]) == ""

    def test_formats_single_category(self):
        items = [
            {"category": "preference", "content": "偏好APA引用格式", "confidence": 0.9},
        ]
        result = format_knowledge_for_prompt(items)
        assert "<academic_memory>" in result
        assert "偏好APA引用格式" in result
        assert "用户偏好" in result

    def test_formats_multiple_categories(self):
        items = [
            {"category": "preference", "content": "偏好APA", "confidence": 0.9},
            {"category": "context", "content": "研究方向：NLP", "confidence": 0.8},
            {"category": "goal", "content": "完成毕业论文", "confidence": 0.95},
        ]
        result = format_knowledge_for_prompt(items)
        assert "用户偏好" in result
        assert "研究上下文" in result
        assert "研究目标" in result


class TestParseKnowledgeJson:
    def test_parses_plain_json(self):
        text = '[{"category": "preference", "content": "APA", "confidence": 0.9}]'
        result = _parse_knowledge_json(text)
        assert len(result) == 1
        assert result[0]["content"] == "APA"

    def test_parses_fenced_json(self):
        text = '```json\n[{"category": "context", "content": "NLP", "confidence": 0.8}]\n```'
        result = _parse_knowledge_json(text)
        assert len(result) == 1

    def test_returns_empty_on_invalid(self):
        assert _parse_knowledge_json("not json") == []

    def test_returns_empty_on_dict(self):
        assert _parse_knowledge_json('{"key": "value"}') == []


class TestLoadUserMemory:
    @patch("src.agents.middleware.memory.get_db_session")
    async def test_returns_empty_on_error(self, mock_session):
        mock_session.side_effect = Exception("DB error")
        result = await load_user_memory("user1")
        assert result == []


class TestExtractAndPersistKnowledge:
    @patch("src.agents.middleware.memory.create_chat_model")
    @patch("src.agents.middleware.memory.get_db_session")
    async def test_returns_zero_on_llm_failure(self, mock_session, mock_model):
        mock_model.side_effect = Exception("LLM unavailable")
        count = await extract_and_persist_knowledge("user1", "some text")
        assert count == 0
```

---

### Task 3: AcademicAgentState + ThesisLeadAgent

Create the unified state schema and the LangGraph-based ThesisLeadAgent.

**Files:**
- Modify: `src/agents/thread_state.py` (keep existing, no changes — it already has what we need)
- Create: `src/agents/thesis_lead_agent.py`
- Create: `src/agents/graphs/__init__.py`
- Create: `src/agents/graphs/thesis/__init__.py`
- Test: `tests/agents/test_thesis_lead_agent.py`

**Implementation:**

```python
# src/agents/thesis_lead_agent.py
"""ThesisLeadAgent — LangGraph-based orchestrator for THESIS workspace features."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph

from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

# Feature IDs that this agent can route to
THESIS_FEATURE_IDS = (
    "deep_research",
    "literature_management",
    "opening_research",
    "thesis_writing",
    "figure_generation",
    "compile_export",
)


def _build_system_prompt(
    workspace_name: str,
    discipline: str | None,
    memory_text: str | None,
) -> str:
    """Build system prompt with memory injection."""
    parts = [
        "你是 AcademiaGPT THESIS 工作区的学术助手。",
        f"当前工作区：{workspace_name}",
    ]
    if discipline:
        parts.append(f"学科领域：{discipline}")
    if memory_text:
        parts.append(f"\n{memory_text}")
    return "\n".join(parts)


async def execute_thesis_feature_graph(
    feature_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Entry point: route a thesis feature to its LangGraph sub-graph.

    Args:
        feature_id: One of THESIS_FEATURE_IDS
        payload: Feature execution payload (workspace_id, params, etc.)
        user_id: For memory loading

    Returns:
        Feature execution result dict
    """
    from src.agents.middleware.memory import (
        format_knowledge_for_prompt,
        load_user_memory,
    )

    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    discipline = payload.get("workspace_discipline")

    # Load user memory
    memory_items: list[dict] = []
    if user_id:
        memory_items = await load_user_memory(user_id, workspace_id)
    memory_text = format_knowledge_for_prompt(memory_items) if memory_items else None

    # Build initial state
    system_prompt = _build_system_prompt(workspace_name, discipline, memory_text)

    initial_state: dict[str, Any] = {
        "messages": [SystemMessage(content=system_prompt)],
        "workspace_id": workspace_id,
        "workspace_type": "thesis",
        "discipline": discipline,
        "knowledge_context": memory_text,
    }

    # Route to feature-specific graph
    graph_fn = _FEATURE_GRAPH_REGISTRY.get(feature_id)
    if graph_fn is None:
        raise ValueError(f"No LangGraph sub-graph registered for feature: {feature_id}")

    return await graph_fn(initial_state, payload)


# Registry: feature_id -> async callable(initial_state, payload) -> result
_FEATURE_GRAPH_REGISTRY: dict[str, Any] = {}


def register_feature_graph(feature_id: str):
    """Decorator to register a feature graph function."""
    def decorator(fn):
        _FEATURE_GRAPH_REGISTRY[feature_id] = fn
        return fn
    return decorator
```

**Tests:**

```python
# tests/agents/test_thesis_lead_agent.py
"""Tests for ThesisLeadAgent routing."""

import pytest
from unittest.mock import AsyncMock, patch

from src.agents.thesis_lead_agent import (
    THESIS_FEATURE_IDS,
    _build_system_prompt,
    execute_thesis_feature_graph,
    register_feature_graph,
    _FEATURE_GRAPH_REGISTRY,
)


class TestBuildSystemPrompt:
    def test_basic_prompt(self):
        result = _build_system_prompt("我的论文", None, None)
        assert "我的论文" in result
        assert "THESIS" in result

    def test_with_discipline(self):
        result = _build_system_prompt("论文", "计算机科学", None)
        assert "计算机科学" in result

    def test_with_memory(self):
        result = _build_system_prompt("论文", None, "<academic_memory>\n偏好APA\n</academic_memory>")
        assert "academic_memory" in result


class TestFeatureRouting:
    def test_all_feature_ids_defined(self):
        assert len(THESIS_FEATURE_IDS) == 6
        assert "deep_research" in THESIS_FEATURE_IDS
        assert "compile_export" in THESIS_FEATURE_IDS

    async def test_raises_for_unknown_feature(self):
        with pytest.raises(ValueError, match="No LangGraph sub-graph"):
            await execute_thesis_feature_graph(
                "nonexistent",
                {"workspace_id": "w1"},
            )

    async def test_routes_to_registered_graph(self):
        mock_fn = AsyncMock(return_value={"success": True})
        _FEATURE_GRAPH_REGISTRY["_test_feature"] = mock_fn
        try:
            result = await execute_thesis_feature_graph(
                "_test_feature",
                {"workspace_id": "w1", "workspace_name": "test"},
            )
            assert result["success"] is True
            mock_fn.assert_called_once()
        finally:
            _FEATURE_GRAPH_REGISTRY.pop("_test_feature", None)
```

---

### Task 4: Memory Compaction Service

Implement the /compact-style memory compaction mechanism.

**Files:**
- Create: `src/services/memory_compaction.py`
- Test: `tests/services/test_memory_compaction.py`

**Implementation:**

```python
# src/services/memory_compaction.py
"""Memory compaction — merge, deduplicate, and archive stale knowledge."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)

COMPACT_PROMPT = """你是一个记忆压缩系统。将以下用户知识条目合并、去重、归纳为更精炼的集合。

当前知识条目:
{entries_json}

要求:
1. 合并语义相似的条目，保留高置信度值
2. 将多个相关上下文条目归纳为一条阶段性摘要
3. 移除过时或矛盾的条目
4. 保留所有偏好类条目（这些通常不过时）

返回 JSON:
{{
  "compacted": [
    {{"category": "...", "content": "...", "confidence": 0.0-1.0}}
  ],
  "summary": "一段话描述用户当前研究进度全景"
}}

仅返回 JSON，不要其他内容。"""


async def compact_user_memory(
    user_id: str,
    *,
    workspace_context: str | None = None,
) -> dict[str, Any]:
    """Compact user memory entries.

    Returns:
        {"compacted_count": int, "archived_count": int, "summary": str}
    """
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    async with get_db_session() as db:
        service = KnowledgeService(db)
        entries = await service.list_active(user_id, min_confidence=0.0, limit=100)

        if len(entries) < 10:
            return {"compacted_count": 0, "archived_count": 0, "summary": ""}

        # Prepare entries for LLM
        entries_data = [
            {"category": e.category.value if hasattr(e.category, "value") else str(e.category),
             "content": e.content,
             "confidence": e.confidence}
            for e in entries
        ]

        try:
            from src.models.factory import create_chat_model
            model = create_chat_model("default", temperature=0.1)
            prompt = COMPACT_PROMPT.format(entries_json=json.dumps(entries_data, ensure_ascii=False))
            response = await model.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            result = _parse_compact_result(content)
        except Exception:
            logger.exception("LLM compaction failed, falling back to archive-only")
            archived = await service.archive_low_confidence(user_id, threshold=0.5)
            return {"compacted_count": 0, "archived_count": archived, "summary": ""}

        # Deactivate all current entries
        for entry in entries:
            entry.is_active = False
        await db.flush()

        # Write compacted entries
        compacted_items = result.get("compacted", [])
        count = 0
        for item in compacted_items:
            cat = item.get("category", "")
            text = item.get("content", "")
            conf = float(item.get("confidence", 0.7))
            if not text:
                continue
            try:
                KnowledgeCategory(cat)
            except ValueError:
                continue
            await service.upsert(
                user_id, cat, text,
                confidence=conf,
                source="compaction",
                workspace_context=workspace_context,
            )
            count += 1

        # Add compaction summary
        summary = result.get("summary", "")
        if summary:
            await service.upsert(
                user_id,
                KnowledgeCategory.CONTEXT,
                summary,
                confidence=0.9,
                source="compaction_summary",
                workspace_context=workspace_context,
            )

        await db.commit()
        return {
            "compacted_count": count,
            "archived_count": len(entries),
            "summary": summary,
        }


def _parse_compact_result(text: str) -> dict[str, Any]:
    """Parse LLM compaction response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"compacted": [], "summary": ""}
```

**Tests:**

```python
# tests/services/test_memory_compaction.py
"""Tests for memory compaction."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.memory_compaction import _parse_compact_result, compact_user_memory


class TestParseCompactResult:
    def test_valid_json(self):
        text = '{"compacted": [{"category": "preference", "content": "APA", "confidence": 0.9}], "summary": "ok"}'
        result = _parse_compact_result(text)
        assert len(result["compacted"]) == 1
        assert result["summary"] == "ok"

    def test_fenced_json(self):
        text = '```json\n{"compacted": [], "summary": "test"}\n```'
        result = _parse_compact_result(text)
        assert result["summary"] == "test"

    def test_invalid_returns_empty(self):
        result = _parse_compact_result("not json")
        assert result["compacted"] == []
        assert result["summary"] == ""


class TestCompactUserMemory:
    @patch("src.services.memory_compaction.get_db_session")
    async def test_skips_when_few_entries(self, mock_session):
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock()

        with patch("src.services.memory_compaction.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=[])
            result = await compact_user_memory("user1")
            assert result["compacted_count"] == 0
```

---

## Phase 2: Feature Sub-Graphs — LLM Upgrade

### Task 5: Literature Management LangGraph Sub-Graph

Upgrade from pure Counter statistics to LLM-powered topic clustering and analysis.

**Files:**
- Create: `src/agents/graphs/thesis/literature_management.py`
- Test: `tests/agents/graphs/thesis/test_literature_management.py`

**Implementation:**

```python
# src/agents/graphs/thesis/literature_management.py
"""Literature Management sub-graph — LLM-powered analysis replacing template stats."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from src.agents.thesis_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)


@register_feature_graph("literature_management")
async def literature_management_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute literature management with LLM-enhanced analysis.

    Pipeline: load literature -> compute stats -> LLM topic clustering -> LLM recommendations
    Falls back to template mode if LLM unavailable.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    focus_topic = str(payload.get("params", {}).get("topic", payload.get("workspace_name", "")))

    # Step 1: Load literature
    literature = await _load_literature(workspace_id)

    # Step 2: Compute base statistics (always works, no LLM needed)
    stats = _compute_statistics(literature, focus_topic)

    # Step 3: LLM-powered analysis (with fallback)
    llm_analysis = await _llm_analyze_literature(literature, focus_topic, initial_state.get("knowledge_context"))

    # Merge LLM analysis into stats
    if llm_analysis:
        stats["topic_clusters"] = llm_analysis.get("topic_clusters", [])
        stats["quality_assessment"] = llm_analysis.get("quality_assessment", "")
        stats["smart_recommendations"] = llm_analysis.get("recommendations", [])
        stats["generation_mode"] = "llm"
    else:
        stats["generation_mode"] = "template_fallback"

    stats["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    return stats


async def _load_literature(workspace_id: str) -> list[dict[str, Any]]:
    """Load workspace literature from DB."""
    from src.database import get_db_session
    from src.services.literature_service import LiteratureService

    try:
        async with get_db_session() as db:
            service = LiteratureService(db)
            response = await service.list_literature(workspace_id, offset=0, limit=120)
        items = response.get("items")
        return items if isinstance(items, list) else []
    except Exception:
        logger.exception("Failed to load literature")
        return []


def _compute_statistics(literature: list[dict], focus_topic: str) -> dict[str, Any]:
    """Compute base statistics (no LLM needed)."""
    total = len(literature)
    if total == 0:
        return {
            "summary": {"total": 0, "core_count": 0, "focus_topic": focus_topic},
            "top_cited": [],
            "by_source": {},
            "by_year": {},
            "quality_check": {"missing_abstract": 0, "missing_doi": 0},
            "recommended_actions": ["添加更多参考文献到工作区"],
        }

    core_count = sum(1 for p in literature if (p.get("citations") or 0) >= 10)
    by_source = dict(Counter(str(p.get("source") or "unknown") for p in literature))
    by_year = dict(Counter(str(p.get("year") or "unknown") for p in literature))
    missing_abstract = sum(1 for p in literature if not p.get("abstract"))
    missing_doi = sum(1 for p in literature if not p.get("doi"))

    sorted_by_citations = sorted(literature, key=lambda p: p.get("citations") or 0, reverse=True)
    top_cited = [
        {"title": p.get("title", ""), "citations": p.get("citations", 0), "year": p.get("year")}
        for p in sorted_by_citations[:10]
    ]

    return {
        "summary": {
            "total": total,
            "core_count": core_count,
            "focus_topic": focus_topic,
            "avg_citations": round(sum(p.get("citations", 0) for p in literature) / total, 1),
        },
        "top_cited": top_cited,
        "by_source": by_source,
        "by_year": by_year,
        "quality_check": {"missing_abstract": missing_abstract, "missing_doi": missing_doi},
        "recommended_actions": _build_recommendations(total, missing_abstract, missing_doi, core_count),
    }


def _build_recommendations(total: int, missing_abstract: int, missing_doi: int, core_count: int) -> list[str]:
    """Rule-based recommendations."""
    actions: list[str] = []
    if total < 15:
        actions.append(f"当前仅 {total} 篇文献，建议补充至 15 篇以上")
    if missing_abstract > total * 0.3:
        actions.append(f"{missing_abstract} 篇缺少摘要，建议补充")
    if missing_doi > total * 0.3:
        actions.append(f"{missing_doi} 篇缺少 DOI，影响引用规范性")
    if core_count < 3:
        actions.append("核心文献不足 3 篇，建议添加高引用量文献")
    return actions or ["文献库质量良好"]


LLM_ANALYSIS_PROMPT = """你是学术文献分析专家。分析以下文献列表，返回 JSON:

文献列表:
{literature_summary}

用户研究方向: {focus_topic}
{memory_context}

返回格式:
{{
  "topic_clusters": [
    {{"name": "主题名", "papers_count": 3, "description": "简述"}}
  ],
  "quality_assessment": "对文献库整体质量的评估（2-3句话）",
  "recommendations": ["具体改进建议1", "具体改进建议2"]
}}

仅返回 JSON。"""


async def _llm_analyze_literature(
    literature: list[dict],
    focus_topic: str,
    memory_context: str | None,
) -> dict[str, Any] | None:
    """LLM-powered literature analysis. Returns None on failure."""
    if not literature:
        return None

    try:
        from src.models.factory import create_chat_model
        model = create_chat_model("default", temperature=0.3)
    except Exception:
        return None

    # Prepare literature summary (limit to avoid token overflow)
    summaries = []
    for p in literature[:50]:
        title = p.get("title", "Unknown")
        year = p.get("year", "")
        citations = p.get("citations", 0)
        abstract = (p.get("abstract") or "")[:200]
        summaries.append(f"- {title} ({year}, cited {citations}x): {abstract}")
    lit_text = "\n".join(summaries)

    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = LLM_ANALYSIS_PROMPT.format(
        literature_summary=lit_text,
        focus_topic=focus_topic,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("LLM literature analysis failed")
        return None


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
```

**Tests:**

```python
# tests/agents/graphs/thesis/test_literature_management.py
"""Tests for literature management sub-graph."""

import pytest
from src.agents.graphs.thesis.literature_management import (
    _compute_statistics,
    _build_recommendations,
    _parse_json_response,
)


class TestComputeStatistics:
    def test_empty_literature(self):
        result = _compute_statistics([], "NLP")
        assert result["summary"]["total"] == 0

    def test_with_papers(self):
        papers = [
            {"title": "Paper A", "citations": 50, "year": "2024", "source": "Scopus", "abstract": "abc", "doi": "10.1"},
            {"title": "Paper B", "citations": 5, "year": "2023", "source": "Scopus", "abstract": None, "doi": None},
        ]
        result = _compute_statistics(papers, "NLP")
        assert result["summary"]["total"] == 2
        assert result["summary"]["core_count"] == 1
        assert result["quality_check"]["missing_abstract"] == 1
        assert result["quality_check"]["missing_doi"] == 1

    def test_top_cited_sorted(self):
        papers = [
            {"title": "Low", "citations": 1, "year": "2024"},
            {"title": "High", "citations": 100, "year": "2024"},
        ]
        result = _compute_statistics(papers, "test")
        assert result["top_cited"][0]["title"] == "High"


class TestBuildRecommendations:
    def test_low_count(self):
        recs = _build_recommendations(5, 0, 0, 3)
        assert any("15" in r for r in recs)

    def test_all_good(self):
        recs = _build_recommendations(20, 0, 0, 5)
        assert recs == ["文献库质量良好"]


class TestParseJsonResponse:
    def test_valid(self):
        assert _parse_json_response('{"key": "val"}') == {"key": "val"}

    def test_fenced(self):
        assert _parse_json_response('```json\n{"k": 1}\n```') == {"k": 1}

    def test_invalid(self):
        assert _parse_json_response("not json") is None
```

---

### Task 6: Opening Research LangGraph Sub-Graph

Upgrade from single LLM call to 3-step pipeline: status analysis → methodology planning → section generation.

**Files:**
- Create: `src/agents/graphs/thesis/opening_research.py`
- Test: `tests/agents/graphs/thesis/test_opening_research.py`

**Implementation:** Same pattern as Task 5. Three sequential LLM nodes:
1. `analyze_research_status` — Analyze research landscape based on literature + memory context
2. `plan_methodology` — Plan research methodology and approach
3. `generate_sections` — Generate report sections with proper citations

Each node has template fallback. Output combined into artifact payload.

---

### Task 7: Figure Generation LangGraph Sub-Graph

Upgrade from direct code generation to LLM-driven planning: analyze chapter → plan figure → generate code.

**Files:**
- Create: `src/agents/graphs/thesis/figure_generation.py`
- Test: `tests/agents/graphs/thesis/test_figure_generation.py`

**Implementation:** Two LLM nodes:
1. `plan_figure` — LLM analyzes chapter content and plans figure type, data, layout
2. `generate_figure_code` — LLM generates Mermaid/Python/Kling code based on plan

Retains existing degraded mode fallback.

---

### Task 8: Compile Export LangGraph Sub-Graph

Add LLM consistency review and auto-generated abstract/keywords.

**Files:**
- Create: `src/agents/graphs/thesis/compile_export.py`
- Test: `tests/agents/graphs/thesis/test_compile_export.py`

**Implementation:** Two LLM nodes added to existing pipeline:
1. `review_consistency` — LLM reviews chapter coherence, citation consistency, terminology uniformity
2. `generate_abstract_keywords` — LLM generates abstract and keywords from assembled content

Existing LaTeX assembly and compilation logic reused from `thesis_feature_service.py`.

---

### Task 9: Thesis Writing Enhancement

Add self-review and revision loop to existing LangGraph workflow.

**Files:**
- Modify: `src/thesis/workflow/` (add review node to existing graph)
- Create: `src/agents/graphs/thesis/thesis_writing.py` (bridge to existing workflow)
- Test: `tests/agents/graphs/thesis/test_thesis_writing.py`

**Implementation:** Adds a `review_section` node after `section_writer` that:
1. LLM reviews written section for logical coherence, citation completeness
2. If issues found, loops back to `section_writer` with revision instructions (max 2 revisions)
3. Injects user memory (citation style preferences, etc.) into writer prompt

---

### Task 10: Deep Research LangGraph Migration

Migrate from ParallelExecutor to LangGraph native parallel nodes.

**Files:**
- Create: `src/agents/graphs/thesis/deep_research.py`
- Test: `tests/agents/graphs/thesis/test_deep_research.py`

**Implementation:**
- Phase 1 nodes (`scout_seminal`, `scout_recent`, `trend_spotter`) → LangGraph parallel fan-out
- Phase 2 node (`gap_miner`) → fan-in after all Phase 1 complete
- Phase 3 node (`synthesizer`) → sequential after Phase 2
- Add `cross_validator` node after synthesis for result verification
- Checkpoint support for long-running executions

---

## Phase 3: End-to-End Closure

### Task 11: Wire Feature Graphs into Task Dispatch

Connect the new LangGraph sub-graphs to the existing task dispatch system.

**Files:**
- Modify: `src/task/tasks/base.py` (`_dispatch_task` — add langgraph routing)
- Modify: `src/task/handlers/workspace_feature_handler.py` (call LangGraph first, fallback to handler)
- Test: `tests/task/test_langgraph_dispatch.py`

**Implementation:**

In `execute_workspace_feature()`, before calling `execute_registered_feature()`:
1. Check if feature has a registered LangGraph sub-graph
2. If yes, try `execute_thesis_feature_graph(feature_id, payload)`
3. If LangGraph execution fails, fallback to existing handler
4. After execution, trigger async memory extraction

---

### Task 12: Artifact Versioning

Add version tracking to artifacts.

**Files:**
- Modify: `src/database/models/artifact.py` (add `version` and `parent_id` columns)
- Modify: `src/academic/services/artifact_service.py` (version-aware create)
- Test: `tests/academic/services/test_artifact_versioning.py`

**Implementation:**
- `version: int` column (default 1), auto-incremented when same workspace+type+title exists
- `parent_id: str | None` FK to previous version
- `ArtifactService.create()` checks for existing artifact with same workspace_id+type, creates new version

---

### Task 13: Integration Verification + Release Gate

Run full regression and update release gate.

**Files:**
- Modify: `src/services/release_gate_service.py` (add THESIS upgrade checks)
- Test: run all tests

**Verification:**
```bash
pytest tests/ -v --tb=short
```

Expected: All new + existing tests pass.

Release gate checks to add:
- `thesis_langgraph_routing`: LangGraph sub-graph dispatch active
- `academic_memory_middleware`: Memory load/persist cycle functional
- `memory_compaction`: Compaction service operational
- `literature_management_llm`: LLM analysis in literature management
- `artifact_versioning`: Version tracking in artifact creation
