# AcademiaGPT v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete AcademiaGPT v2 as a production-ready multi-user academic AI system with Lead Agent, PDF indexing, Next.js frontend, and authentication.

**Architecture:** Gateway (FastAPI) + LangGraph Agent + PostgreSQL + Redis + Next.js 16. Docker Compose deployment. Index-based RAG (no embeddings). Multi-provider LLM support.

**Tech Stack:** Python 3.12+, LangGraph, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Redis 7, Next.js 16, React 19, TypeScript, Tailwind CSS, Zustand.

**Design Document:** `docs/plans/2026-03-08-academiagpt-v2-refinement-design.md`

**Reference Projects:**
- DeerFlow: `/home/cjz/deer-flow`
- AcademiaGPT v1: `/home/cjz/AcademiaGPT`

---

## Phase 1: Lead Agent + Skills (Core AI)

### Task 1.1: Configuration System Enhancement

**Files:**
- Modify: `backend/src/config/app_config.py`
- Create: `backend/src/config/llm_config.py`
- Test: `backend/tests/config/test_llm_config.py`

**Step 1: Write the failing test**

```python
# tests/config/test_llm_config.py
"""Tests for LLM configuration loading."""

import json
import pytest


def test_parse_gen_models_from_env(monkeypatch):
    """Test parsing LLM_GEN_MODELS from environment."""
    from src.config.llm_config import get_gen_models

    models_json = json.dumps([
        {
            "id": "test-model",
            "name": "Test Model",
            "model": "openai/test-model",
            "api_key": "sk-test",
            "base_url": "https://api.test.com/v1",
            "temp": 0.7,
        }
    ])
    monkeypatch.setenv("LLM_GEN_MODELS", models_json)

    models = get_gen_models()
    assert len(models) == 1
    assert models[0].id == "test-model"
    assert models[0].api_key == "sk-test"


def test_get_model_full_config_not_found():
    """Test error when model not found."""
    from src.config.llm_config import get_model_full_config

    with pytest.raises(ValueError, match="未找到模型"):
        get_model_full_config("nonexistent-model")
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/config/test_llm_config.py -v
```
Expected: FAIL with "ModuleNotFoundError" or similar

**Step 3: Write minimal implementation**

```python
# src/config/llm_config.py
"""LLM configuration - loads model configs from environment variables.

Compatible with original AcademiaGPT config format.
"""

import json
import logging
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    """Model configuration."""
    id: str
    display_name: str
    model_string: str
    api_key: str
    base_url: str
    max_tokens: int = 4096
    temperature_default: float = 0.7
    supports_tools: bool = False
    supports_json_mode: bool = True


# Cached models
_cached_gen_models: list[ModelConfig] | None = None
_cached_tool_models: list[ModelConfig] | None = None


def _parse_model(data: dict) -> ModelConfig:
    """Parse model config from env format."""
    required = ["id", "model", "api_key", "base_url"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ValueError(f"模型配置缺少必选字段: {missing}")

    return ModelConfig(
        id=data["id"],
        display_name=data.get("name", data["id"]),
        model_string=data["model"],
        api_key=data["api_key"],
        base_url=data["base_url"],
        max_tokens=data.get("max_tokens", 4096),
        temperature_default=data.get("temp", 0.7),
        supports_tools=data.get("supports_tools", False),
        supports_json_mode=data.get("supports_json_mode", True),
    )


def _load_models() -> None:
    """Load models from environment variables."""
    global _cached_gen_models, _cached_tool_models

    import os

    _cached_gen_models = []
    _cached_tool_models = []

    # Load GEN_MODELS
    gen_json = os.getenv("LLM_GEN_MODELS", "[]")
    try:
        for m in json.loads(gen_json):
            try:
                _cached_gen_models.append(_parse_model(m))
            except ValueError as e:
                logger.warning(f"跳过无效模型配置: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"LLM_GEN_MODELS JSON 解析失败: {e}")

    # Load TOOL_MODELS
    tool_json = os.getenv("LLM_TOOL_MODELS", "[]")
    try:
        for m in json.loads(tool_json):
            try:
                _cached_tool_models.append(_parse_model(m))
            except ValueError as e:
                logger.warning(f"跳过无效工具模型配置: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"LLM_TOOL_MODELS JSON 解析失败: {e}")

    logger.info(f"加载了 {len(_cached_gen_models)} 个生成模型, {len(_cached_tool_models)} 个工具模型")


def get_gen_models() -> list[ModelConfig]:
    """Get all generation models."""
    if _cached_gen_models is None:
        _load_models()
    return _cached_gen_models


def get_tool_models() -> list[ModelConfig]:
    """Get all tool models."""
    if _cached_tool_models is None:
        _load_models()
    return _cached_tool_models


def get_model_config(model_id: str) -> Optional[ModelConfig]:
    """Get model config by ID."""
    for m in get_gen_models() + get_tool_models():
        if m.id == model_id:
            return m
    return None


def get_model_full_config(model_id: str) -> dict:
    """Get full model config as dict."""
    config = get_model_config(model_id)
    if not config:
        raise ValueError(f"未找到模型: {model_id}")
    return {
        "api_key": config.api_key,
        "base_url": config.base_url,
        "model": config.model_string,
        "temperature": config.temperature_default,
        "max_tokens": config.max_tokens,
        "supports_json_mode": config.supports_json_mode,
    }


def reload_models() -> None:
    """Reload models from environment."""
    global _cached_gen_models, _cached_tool_models
    _cached_gen_models = None
    _cached_tool_models = None
    _load_models()
```

**Step 4: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/config/test_llm_config.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/config/llm_config.py tests/config/test_llm_config.py
git commit -m "feat(config): add LLM configuration loader from env variables"
```

---

### Task 1.2: Update Model Factory

**Files:**
- Modify: `backend/src/models/factory.py`
- Test: `backend/tests/models/test_factory.py`

**Step 1: Write the failing test**

```python
# tests/models/test_factory.py
"""Tests for model factory."""

import pytest


def test_create_chat_model_openai_compatible(monkeypatch):
    """Test creating OpenAI-compatible model."""
    from src.models.factory import create_chat_model

    monkeypatch.setenv("LLM_GEN_MODELS", '[{"id":"test-gpt","name":"Test","model":"gpt-4o","api_key":"sk-test","base_url":"https://api.openai.com/v1"}]')

    # Force reload
    from src.config import llm_config
    llm_config.reload_models()

    model = create_chat_model("test-gpt")
    assert model is not None


def test_create_chat_model_with_thinking(monkeypatch):
    """Test creating model with thinking enabled."""
    from src.models.factory import create_chat_model

    monkeypatch.setenv("LLM_GEN_MODELS", '[{"id":"claude-test","name":"Claude","model":"claude-sonnet-4-20250514","api_key":"sk-test","base_url":"https://api.anthropic.com","supports_thinking":true}]')

    from src.config import llm_config
    llm_config.reload_models()

    model = create_chat_model("claude-test", thinking_enabled=True)
    assert model is not None
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/models/test_factory.py -v
```

**Step 3: Write minimal implementation**

```python
# src/models/factory.py (replace entire file)
"""Model factory for creating LLM instances."""

from typing import Optional

from langchain_core.language_models import BaseChatModel

from src.config.llm_config import get_model_config, get_model_full_config


def create_chat_model(
    model_id: str = "gpt-4o",
    temperature: Optional[float] = None,
    thinking_enabled: bool = False,
) -> BaseChatModel:
    """Create a chat model instance based on model_id.

    Args:
        model_id: Model identifier (from LLM_GEN_MODELS or LLM_TOOL_MODELS)
        temperature: Override temperature (uses model default if None)
        thinking_enabled: Enable extended thinking (Claude only)

    Returns:
        Configured chat model instance
    """
    config = get_model_full_config(model_id)
    model_string = config["model"]
    temp = temperature if temperature is not None else config["temperature"]

    # Determine provider from model string or base_url
    is_anthropic = "anthropic" in config["base_url"] or "claude" in model_string

    if is_anthropic:
        from langchain_anthropic import ChatAnthropic

        kwargs = {
            "model": model_string,
            "api_key": config["api_key"],
            "max_tokens": config["max_tokens"],
            "temperature": temp,
        }

        if thinking_enabled:
            kwargs["thinking_budget"] = 10000
            kwargs["betas"] = ["interleaved-thinking-2025-05-14"]

        return ChatAnthropic(**kwargs)
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_string,
            api_key=config["api_key"],
            base_url=config["base_url"],
            max_tokens=config["max_tokens"],
            temperature=temp,
        )
```

**Step 4: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/models/test_factory.py -v
```

**Step 5: Commit**

```bash
git add src/models/factory.py tests/models/test_factory.py
git commit -m "feat(models): update factory to use dynamic config from env"
```

---

### Task 1.3: Complete WorkspaceContextMiddleware

**Files:**
- Modify: `backend/src/agents/middlewares/workspace_context.py`
- Test: `backend/tests/agents/middlewares/test_workspace_context.py`

**Step 1: Write the failing test**

```python
# tests/agents/middlewares/test_workspace_context.py
"""Tests for WorkspaceContextMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.thread_state import ThreadState
from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware


@pytest.mark.asyncio
async def test_workspace_context_loads_workspace():
    """Test that middleware loads workspace configuration."""
    # Mock workspace service
    mock_workspace = MagicMock()
    mock_workspace.id = "ws-123"
    mock_workspace.type = "sci"
    mock_workspace.discipline = "computer_science"
    mock_workspace.config = {"citation_style": "APA"}

    mock_service = AsyncMock()
    mock_service.get = AsyncMock(return_value=mock_workspace)

    middleware = WorkspaceContextMiddleware(mock_service)

    state = ThreadState(workspace_id="ws-123")
    result = await middleware.before_model(state, {})

    assert result["workspace_type"] == "sci"
    assert result["discipline"] == "computer_science"


@pytest.mark.asyncio
async def test_workspace_context_no_workspace_id():
    """Test middleware skips when no workspace_id."""
    mock_service = AsyncMock()
    middleware = WorkspaceContextMiddleware(mock_service)

    state = ThreadState()
    result = await middleware.before_model(state, {})

    # Should return unchanged state
    assert "workspace_type" not in result or result.get("workspace_type") is None
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/agents/middlewares/test_workspace_context.py -v
```

**Step 3: Update implementation**

```python
# src/agents/middlewares/workspace_context.py
"""Workspace context middleware for loading workspace configuration."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class WorkspaceContextMiddleware(Middleware):
    """Middleware that loads and injects workspace context.

    This middleware:
    1. Checks if workspace_id is present in state
    2. Loads workspace configuration from database
    3. Injects workspace type, discipline, and config into state
    """

    def __init__(self, workspace_service):
        """Initialize with workspace service.

        Args:
            workspace_service: Service for workspace CRUD operations
        """
        self.workspace_service = workspace_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load workspace context and inject into state."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        workspace = await self.workspace_service.get(workspace_id)
        if not workspace:
            return dict(state)

        return {
            **dict(state),
            "workspace_type": workspace.type,
            "discipline": workspace.discipline,
            "_workspace_config": workspace.config or {},
        }
```

**Step 4: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/agents/middlewares/test_workspace_context.py -v
```

**Step 5: Commit**

```bash
git add src/agents/middlewares/workspace_context.py tests/agents/middlewares/test_workspace_context.py
git commit -m "feat(middleware): complete WorkspaceContextMiddleware with tests"
```

---

### Task 1.4: Complete LiteratureContextMiddleware (Index-Based)

**Files:**
- Modify: `backend/src/agents/middlewares/literature_context.py`
- Create: `backend/src/academic/literature/index_service.py`
- Test: `backend/tests/agents/middlewares/test_literature_context.py`

**Step 1: Write the failing test**

```python
# tests/agents/middlewares/test_literature_context.py
"""Tests for LiteratureContextMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.thread_state import ThreadState
from src.agents.middlewares.literature_context import LiteratureContextMiddleware


@pytest.mark.asyncio
async def test_literature_context_injects_toc_summary():
    """Test that middleware injects literature TOC summary."""
    mock_service = AsyncMock()
    mock_service.get_workspace_toc_summary = AsyncMock(return_value="""
## 文献库概览

### [1] Attention Is All You Need (2017)
- 目录: Introduction, Background, Model Architecture, Experiments, Conclusion

### [2] BERT (2019)
- 目录: Introduction, Related Work, BERT, Experiments, Conclusion
""")

    middleware = LiteratureContextMiddleware(mock_service)

    state = ThreadState(workspace_id="ws-123")
    result = await middleware.before_model(state, {})

    assert "_literature_context" in result
    assert "Attention Is All You Need" in result["_literature_context"]
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/agents/middlewares/test_literature_context.py -v
```

**Step 3: Create index service**

```python
# src/academic/literature/index_service.py
"""Index-based literature navigation service (no embeddings)."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Paper, WorkspacePaper


class LiteratureIndexService:
    """Service for index-based literature navigation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        """Get TOC summary for all papers in workspace.

        Returns formatted text with each paper's title and TOC.
        """
        result = await self.db.execute(
            select(Paper)
            .join(WorkspacePaper)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .order_by(WorkspacePaper.added_at.desc())
        )
        papers = result.scalars().all()

        if not papers:
            return ""

        lines = ["## 文献库概览\n"]
        for i, paper in enumerate(papers, 1):
            lines.append(f"### [{i}] {paper.title} ({paper.year or 'N/A'})")
            if paper.toc:
                toc_items = [item.get("title", "") for item in paper.toc[:5]]
                lines.append(f"- 目录: {', '.join(toc_items)}")
            lines.append("")

        return "\n".join(lines)

    async def get_paper_toc(self, paper_id: str) -> list[dict]:
        """Get table of contents for a paper."""
        result = await self.db.execute(
            select(Paper).where(Paper.id == paper_id)
        )
        paper = result.scalar_one_or_none()
        return paper.toc if paper and paper.toc else []

    async def get_paper_section(
        self,
        paper_id: str,
        section_path: str,
    ) -> Optional[str]:
        """Get content of a specific section by path."""
        from src.database.models import PaperSection

        result = await self.db.execute(
            select(PaperSection)
            .where(PaperSection.paper_id == paper_id)
            .where(PaperSection.section_path == section_path)
        )
        section = result.scalar_one_or_none()
        return section.content if section else None
```

**Step 4: Update middleware**

```python
# src/agents/middlewares/literature_context.py
"""Literature context middleware for index-based retrieval."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class LiteratureContextMiddleware(Middleware):
    """Middleware that injects literature context (index-based, no embeddings)."""

    def __init__(self, index_service):
        """Initialize with literature index service.

        Args:
            index_service: LiteratureIndexService instance
        """
        self.index_service = index_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject literature TOC summary into context."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        # Get TOC summary for all papers in workspace
        toc_summary = await self.index_service.get_workspace_toc_summary(workspace_id)

        return {
            **dict(state),
            "_literature_context": toc_summary,
        }
```

**Step 5: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/agents/middlewares/test_literature_context.py -v
```

**Step 6: Commit**

```bash
git add src/agents/middlewares/literature_context.py src/academic/literature/index_service.py tests/agents/middlewares/test_literature_context.py
git commit -m "feat(literature): add index-based literature context middleware"
```

---

### Task 1.5: Add PaperSection Model and Literature Tools

**Files:**
- Modify: `backend/src/database/models/paper.py`
- Create: `backend/src/academic/literature/tools.py`
- Test: `backend/tests/academic/literature/test_tools.py`

**Step 1: Add PaperSection model**

```python
# Add to src/database/models/paper.py (after PaperChunk class)

class PaperSection(Base, UUIDMixin, TimestampMixin):
    """Paper section for index-based navigation (no embeddings).

    Stores full text of each section for precise retrieval.

    Attributes:
        paper_id: Foreign key to paper
        workspace_id: Foreign key to workspace
        section_title: Human-readable section title
        section_path: Hierarchical path like "3.2.1"
        page_start: Starting page number
        page_end: Ending page number
        content: Full text content of section
        level: Section depth (1 for top-level, 2 for subsection, etc.)
    """

    __tablename__ = "paper_sections"
    __table_args__ = (
        Index("ix_paper_sections_paper_workspace", "paper_id", "workspace_id"),
        Index("ix_paper_sections_path", "paper_id", "section_path"),
    )

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[str] = mapped_column(String(100), nullable=False)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper")
    workspace: Mapped["Workspace"] = relationship("Workspace")

    def __repr__(self) -> str:
        return f"<PaperSection(path={self.section_path}, title={self.section_title})>"
```

**Step 2: Create literature tools**

```python
# src/academic/literature/tools.py
"""Literature navigation tools (index-based, no embeddings)."""

from langchain_core.tools import tool


@tool
def get_paper_toc(paper_id: str) -> str:
    """Get the table of contents for a paper.

    Use this to navigate papers and find relevant sections.

    Args:
        paper_id: The ID of the paper

    Returns:
        Formatted TOC with section paths and titles
    """
    # Implementation will be injected at runtime
    from src.academic.literature import get_index_service

    async def _get_toc():
        service = await get_index_service()
        toc = await service.get_paper_toc(paper_id)
        if not toc:
            return f"未找到论文 {paper_id} 的目录"

        lines = [f"## 论文目录\n"]
        for item in toc:
            level = item.get("level", 1)
            indent = "  " * (level - 1)
            title = item.get("title", "")
            page = item.get("page", "")
            lines.append(f"{indent}- {title} (p.{page})" if page else f"{indent}- {title}")

        return "\n".join(lines)

    import asyncio
    return asyncio.run(_get_toc())


@tool
def get_paper_section(paper_id: str, section_path: str) -> str:
    """Get the full content of a specific section.

    Use get_paper_toc first to find the section path.

    Args:
        paper_id: The ID of the paper
        section_path: Section path like "3.2.1" or "3"

    Returns:
        Full text content of the section
    """
    from src.academic.literature import get_index_service

    async def _get_section():
        service = await get_index_service()
        content = await service.get_paper_section(paper_id, section_path)
        if not content:
            return f"未找到章节 {section_path}"
        return content

    import asyncio
    return asyncio.run(_get_section())


@tool
def search_papers_by_metadata(query: str, workspace_id: str = None) -> str:
    """Search papers by title, authors, or keywords.

    Args:
        query: Search query (title, author name, or keyword)
        workspace_id: Optional workspace ID to limit search

    Returns:
        List of matching papers with basic info
    """
    from src.academic.literature import get_index_service

    async def _search():
        service = await get_index_service()
        papers = await service.search_by_metadata(query, workspace_id)
        if not papers:
            return "未找到匹配的论文"

        lines = ["## 搜索结果\n"]
        for p in papers[:10]:
            lines.append(f"- **{p['title']}** ({p.get('year', 'N/A')})")
            if p.get('authors'):
                lines.append(f"  作者: {', '.join(p['authors'][:3])}")
            lines.append(f"  ID: {p['id']}\n")

        return "\n".join(lines)

    import asyncio
    return asyncio.run(_search())
```

**Step 3: Update Paper model to include TOC field**

```python
# Add to Paper class in src/database/models/paper.py

    # Add after abstract field
    toc: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
```

**Step 4: Commit**

```bash
git add src/database/models/paper.py src/academic/literature/tools.py
git commit -m "feat(literature): add PaperSection model and navigation tools"
```

---

### Task 1.6: Implement Academic Subagents

**Files:**
- Modify: `backend/src/subagents/academic/__init__.py`
- Create: `backend/src/subagents/academic/prompts.py`
- Create: `backend/src/subagents/academic/registry.py`
- Test: `backend/tests/subagents/academic/test_registry.py`

**Step 1: Write the failing test**

```python
# tests/subagents/academic/test_registry.py
"""Tests for academic subagent registry."""

import pytest
from src.subagents.academic.registry import ACADEMIC_SUBAGENTS, get_subagent_config


def test_registry_has_four_subagents():
    """Test that all four academic subagents are registered."""
    assert len(ACADEMIC_SUBAGENTS) == 4
    assert "scout" in ACADEMIC_SUBAGENTS
    assert "writer" in ACADEMIC_SUBAGENTS
    assert "synthesizer" in ACADEMIC_SUBAGENTS
    assert "analyst" in ACADEMIC_SUBAGENTS


def test_get_subagent_config():
    """Test getting subagent config."""
    config = get_subagent_config("scout")
    assert config.name == "Scout"
    assert "semantic_scholar" in str(config.tools).lower()
```

**Step 2: Create prompts file**

```python
# src/subagents/academic/prompts.py
"""System prompts for academic subagents."""

SCOUT_PROMPT = """You are Scout, a literature exploration agent.

Your mission is to discover and expand the literature base:

1. **Search Strategy**
   - Use semantic_scholar_search to find relevant papers
   - Track citation chains (both forward and backward)
   - Identify highly-cited foundational papers

2. **Quality Criteria**
   - Prefer papers from top venues
   - Check citation count and recency
   - Identify seminal works in the field

3. **Output Format**
   Return findings as structured JSON:
   ```json
   {
     "papers_found": [...],
     "citation_chains": [...],
     "research_gaps_identified": [...]
   }
   ```

Focus on thoroughness. Do not rush."""

WRITER_PROMPT = """You are Writer, an academic writing specialist.

Your mission is to produce high-quality academic text:

1. **Writing Standards**
   - Follow the discipline's citation style
   - Use formal academic language
   - Structure arguments logically

2. **Available Tools**
   - get_paper_section: Retrieve specific sections for citation
   - get_paper_toc: Navigate paper structure

3. **Output Guidelines**
   - Cite sources inline: [Author, Year]
   - Maintain coherent flow between paragraphs
   - Balance depth with clarity

Write with precision. Every claim should be supported."""

SYNTHESIZER_PROMPT = """You are Synthesizer, an insight generation agent.

Your mission is to synthesize information and generate novel insights:

1. **Analysis Tasks**
   - Compare methodologies across papers
   - Identify contradictions and agreements
   - Map the evolution of ideas

2. **Insight Generation**
   - Find research gaps
   - Propose novel combinations
   - Suggest future directions

3. **Output Format**
   Return structured analysis:
   ```json
   {
     "key_findings": [...],
     "contradictions": [...],
     "research_gaps": [...],
     "novel_insights": [...]
   }
   ```

Think deeply. Connect dots others miss."""

ANALYST_PROMPT = """You are Analyst, a data and methodology specialist.

Your mission is to analyze experimental designs and statistical methods:

1. **Analysis Capabilities**
   - Evaluate experimental designs
   - Assess statistical validity
   - Identify methodological strengths/weaknesses

2. **Recommendations**
   - Suggest improved methodologies
   - Propose alternative analyses
   - Identify potential confounds

3. **Output Format**
   Return detailed analysis:
   ```json
   {
     "methodology_assessment": {...},
     "statistical_review": {...},
     "recommendations": [...],
     "limitations": [...]
   }
   ```

Be rigorous. Question assumptions."""
```

**Step 3: Create registry**

```python
# src/subagents/academic/registry.py
"""Registry for academic subagents."""

from dataclasses import dataclass, field
from typing import List

from .prompts import SCOUT_PROMPT, WRITER_PROMPT, SYNTHESIZER_PROMPT, ANALYST_PROMPT


@dataclass
class SubagentConfig:
    """Configuration for a subagent."""
    name: str
    description: str
    system_prompt: str
    tools: List[str]
    max_turns: int = 10


ACADEMIC_SUBAGENTS = {
    "scout": SubagentConfig(
        name="Scout",
        description="文献探索Agent，负责扩展文献库、追踪引用链、发现关联论文",
        system_prompt=SCOUT_PROMPT,
        tools=["semantic_scholar_search"],
        max_turns=10,
    ),
    "writer": SubagentConfig(
        name="Writer",
        description="学术写作Agent，按学科规范进行高质量写作",
        system_prompt=WRITER_PROMPT,
        tools=["get_paper_section", "get_paper_toc"],
        max_turns=15,
    ),
    "synthesizer": SubagentConfig(
        name="Synthesizer",
        description="综合分析Agent，从多源信息中生成创新性洞察",
        system_prompt=SYNTHESIZER_PROMPT,
        tools=["get_paper_section", "get_paper_toc"],
        max_turns=10,
    ),
    "analyst": SubagentConfig(
        name="Analyst",
        description="数据分析Agent，进行统计分析和实验设计",
        system_prompt=ANALYST_PROMPT,
        tools=["get_paper_section"],
        max_turns=10,
    ),
}


def get_subagent_config(subagent_type: str) -> SubagentConfig:
    """Get configuration for a specific subagent type."""
    if subagent_type not in ACADEMIC_SUBAGENTS:
        raise ValueError(f"Unknown subagent type: {subagent_type}")
    return ACADEMIC_SUBAGENTS[subagent_type]


def get_all_subagent_types() -> List[str]:
    """Get list of all available subagent types."""
    return list(ACADEMIC_SUBAGENTS.keys())
```

**Step 4: Update __init__.py**

```python
# src/subagents/academic/__init__.py
"""Academic subagents package."""

from .registry import (
    ACADEMIC_SUBAGENTS,
    SubagentConfig,
    get_subagent_config,
    get_all_subagent_types,
)
from .prompts import (
    SCOUT_PROMPT,
    WRITER_PROMPT,
    SYNTHESIZER_PROMPT,
    ANALYST_PROMPT,
)

__all__ = [
    "ACADEMIC_SUBAGENTS",
    "SubagentConfig",
    "get_subagent_config",
    "get_all_subagent_types",
    "SCOUT_PROMPT",
    "WRITER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "ANALYST_PROMPT",
]
```

**Step 5: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/subagents/academic/test_registry.py -v
```

**Step 6: Commit**

```bash
git add src/subagents/academic/ tests/subagents/academic/
git commit -m "feat(subagents): implement academic subagent registry with prompts"
```

---

### Task 1.7: Update Lead Agent with Middleware Chain

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`
- Test: `backend/tests/agents/test_lead_agent.py`

**Step 1: Write the failing test**

```python
# tests/agents/test_lead_agent.py
"""Tests for Lead Agent."""

import pytest
from unittest.mock import patch, MagicMock


def test_make_lead_agent_creates_agent():
    """Test that make_lead_agent creates a valid agent."""
    from src.agents.lead_agent.agent import make_lead_agent

    with patch("src.agents.lead_agent.agent.get_available_tools") as mock_tools:
        mock_tools.return_value = []
        agent = make_lead_agent({"configurable": {"model_name": "gpt-4o"}})

        assert agent is not None


def test_apply_prompt_template_includes_workspace():
    """Test prompt template includes workspace context."""
    from src.agents.lead_agent.agent import apply_prompt_template
    from src.agents.thread_state import ThreadState

    state = ThreadState(
        workspace_type="sci",
        discipline="computer_science",
        _literature_context="## 文献\nTest paper",
    )

    prompt = apply_prompt_template(state, {})

    assert "SCI Paper" in prompt
    assert "Computer Science" in prompt
    assert "Test paper" in prompt
```

**Step 2: Update agent implementation**

```python
# src/agents/lead_agent/agent.py (update key functions)
# The file already has good structure, just need to ensure middleware integration

def build_middlewares(
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
) -> list:
    """Build middleware chain for the agent.

    Order matters! Middlewares execute in order:
    1. WorkspaceContextMiddleware - Load workspace config
    2. LiteratureContextMiddleware - Index-based TOC injection
    3. KnowledgeContextMiddleware - Load artifacts
    4. DisciplineContextMiddleware - Load discipline norms
    5. CitationContextMiddleware - Track citations (after_model only)

    Args:
        workspace_service: Workspace service instance
        index_service: LiteratureIndexService instance
        artifact_service: Artifact service instance
        paper_service: Paper service instance

    Returns:
        List of middleware instances
    """
    middlewares = []

    if workspace_service:
        middlewares.append(WorkspaceContextMiddleware(workspace_service))

    if index_service:
        middlewares.append(LiteratureContextMiddleware(index_service))

    if artifact_service:
        middlewares.append(KnowledgeContextMiddleware(artifact_service))

    middlewares.append(DisciplineContextMiddleware())

    if paper_service:
        middlewares.append(CitationContextMiddleware(paper_service))

    return middlewares
```

**Step 3: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/agents/test_lead_agent.py -v
```

**Step 4: Commit**

```bash
git add src/agents/lead_agent/agent.py tests/agents/test_lead_agent.py
git commit -m "feat(agent): integrate middleware chain into lead agent"
```

---

### Task 1.8: Create Docker Compose Configuration

**Files:**
- Create: `docker-compose.yml`
- Create: `nginx.conf`
- Create: `.env.example`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`

**Step 1: Create docker-compose.yml**

```yaml
# docker-compose.yml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "2026:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - frontend
      - gateway
      - langgraph
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    environment:
      - NEXT_PUBLIC_API_URL=/api
      - NEXT_PUBLIC_LANGGRAPH_URL=/langgraph
    restart: unless-stopped

  gateway:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001
    environment:
      - APP_DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@postgres:5432/academiagpt
      - REDIS_ENABLED=true
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./backend/.env:/app/.env:ro
      - uploads:/app/uploads
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  langgraph:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: langgraph dev --host 0.0.0.0 --port 2024
    environment:
      - APP_DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@postgres:5432/academiagpt
      - REDIS_ENABLED=true
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./backend/.env:/app/.env:ro
      - ./backend/skills:/app/skills:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: academiagpt
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  uploads:
```

**Step 2: Create nginx.conf**

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream frontend {
        server frontend:3000;
    }

    upstream gateway {
        server gateway:8001;
    }

    upstream langgraph {
        server langgraph:2024;
    }

    server {
        listen 80;
        client_max_body_size 100M;

        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
        }

        location /api/ {
            proxy_pass http://gateway/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /langgraph/ {
            proxy_pass http://langgraph/;
            proxy_set_header Host $host;
            proxy_set_header Connection '';
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
            proxy_buffering off;
            proxy_cache off;
        }
    }
}
```

**Step 3: Create .env.example**

```bash
# .env.example
# Database
DB_PASSWORD=your_secure_password_here

# LLM Configuration (JSON format)
LLM_GEN_MODELS=[{"id":"deepseek-v3","name":"DeepSeek V3","model":"deepseek/deepseek-v3","api_key":"sk-xxx","base_url":"https://api.deepseek.com"}]
LLM_TOOL_MODELS=[{"id":"deepseek-v3","name":"DeepSeek V3","model":"deepseek/deepseek-v3","api_key":"sk-xxx","base_url":"https://api.deepseek.com","supports_tools":true}]

# Semantic Scholar API (optional but recommended)
SEMANTIC_SCHOLAR_API_KEY=

# JWT (generate with: python -c "import secrets; print(secrets.token_urlsafe(64))")
APP_JWT_SECRET_KEY=your-jwt-secret-key-here
```

**Step 4: Create backend Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY skills/ ./skills/

# Install dependencies
RUN uv sync --no-dev

# Expose port
EXPOSE 8001 2024

# Default command
CMD ["uvicorn", "src.gateway.app:app", "--host", "0.0.0.0", "--port", "8001"]
```

**Step 5: Create frontend Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

**Step 6: Commit**

```bash
git add docker-compose.yml nginx.conf .env.example backend/Dockerfile frontend/Dockerfile
git commit -m "feat(deploy): add Docker Compose configuration for production"
```

---

## Phase 2: PDF Upload & Index System

### Task 2.1: PDF Extraction Service

**Files:**
- Create: `backend/src/academic/literature/extraction/pdf_extractor.py`
- Create: `backend/src/academic/literature/extraction/__init__.py`
- Test: `backend/tests/academic/literature/test_pdf_extractor.py`

**Step 1: Write the failing test**

```python
# tests/academic/literature/test_pdf_extractor.py
"""Tests for PDF extraction."""

import pytest
from pathlib import Path


def test_extract_toc_from_pdf():
    """Test TOC extraction from PDF."""
    from src.academic.literature.extraction.pdf_extractor import PDFExtractor

    # Use a sample PDF or mock
    extractor = PDFExtractor()

    # This will fail until we implement it
    result = extractor.extract_toc("nonexistent.pdf")
    assert result is not None  # Should return list
```

**Step 2: Create extractor**

```python
# src/academic/literature/extraction/pdf_extractor.py
"""PDF extraction service using PyMuPDF."""

from typing import Optional
from pathlib import Path
import fitz  # PyMuPDF


class PDFExtractor:
    """Extract content and structure from PDF files."""

    def extract_toc(self, pdf_path: str) -> list[dict]:
        """Extract table of contents from PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of TOC items: [{"title": str, "page": int, "level": int}, ...]
        """
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()

        result = []
        for item in toc:
            level, title, page = item
            result.append({
                "title": title,
                "page": page,
                "level": level,
            })

        doc.close()
        return result

    def extract_metadata(self, pdf_path: str) -> dict:
        """Extract metadata from PDF.

        Returns:
            dict with title, authors, etc.
        """
        doc = fitz.open(pdf_path)
        meta = doc.metadata

        result = {
            "title": meta.get("title", ""),
            "authors": meta.get("author", "").split(";") if meta.get("author") else [],
            "page_count": doc.page_count,
        }

        doc.close()
        return result

    def extract_section_content(
        self,
        pdf_path: str,
        page_start: int,
        page_end: Optional[int] = None,
    ) -> str:
        """Extract text content from a page range.

        Args:
            pdf_path: Path to PDF file
            page_start: Starting page (1-indexed)
            page_end: Ending page (inclusive), None for single page

        Returns:
            Extracted text content
        """
        doc = fitz.open(pdf_path)

        if page_end is None:
            page_end = page_start

        # Convert to 0-indexed
        pages = range(page_start - 1, min(page_end, doc.page_count))

        text_parts = []
        for page_num in pages:
            page = doc[page_num]
            text_parts.append(page.get_text())

        doc.close()
        return "\n\n".join(text_parts)

    def split_into_sections(
        self,
        pdf_path: str,
        toc: list[dict],
    ) -> list[dict]:
        """Split PDF into sections based on TOC.

        Args:
            pdf_path: Path to PDF file
            toc: Table of contents from extract_toc()

        Returns:
            List of sections with content
        """
        doc = fitz.open(pdf_path)
        sections = []

        for i, item in enumerate(toc):
            page_start = item["page"]
            # Get end page from next item or last page
            if i + 1 < len(toc):
                page_end = toc[i + 1]["page"] - 1
            else:
                page_end = doc.page_count

            content = self.extract_section_content(pdf_path, page_start, page_end)

            sections.append({
                "title": item["title"],
                "level": item["level"],
                "page_start": page_start,
                "page_end": page_end,
                "content": content,
            })

        doc.close()
        return sections
```

**Step 3: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/academic/literature/test_pdf_extractor.py -v
```

**Step 4: Commit**

```bash
git add src/academic/literature/extraction/ tests/academic/literature/test_pdf_extractor.py
git commit -m "feat(pdf): add PDF extraction service with TOC and section support"
```

---

## Phase 3: Frontend Workbench

### Task 3.1: Create Workspace Store

**Files:**
- Create: `frontend/stores/workspace.ts`
- Create: `frontend/stores/chat.ts`

**Step 1: Create workspace store**

```typescript
// frontend/stores/workspace.ts
import { create } from 'zustand';

interface Workspace {
  id: string;
  name: string;
  type: 'sci' | 'thesis' | 'proposal' | 'grant';
  discipline: string | null;
  description: string | null;
  created_at: string;
}

interface Artifact {
  id: string;
  workspace_id: string;
  type: string;
  title: string | null;
  content: Record<string, unknown>;
  created_at: string;
}

interface Paper {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
}

interface WorkspaceState {
  workspace: Workspace | null;
  artifacts: Artifact[];
  papers: Paper[];
  isLoading: boolean;

  loadWorkspace: (id: string) => Promise<void>;
  addPaper: (paper: Paper) => void;
  addArtifact: (artifact: Artifact) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspace: null,
  artifacts: [],
  papers: [],
  isLoading: false,

  loadWorkspace: async (id: string) => {
    set({ isLoading: true });
    try {
      const response = await fetch(`/api/workspaces/${id}`);
      const workspace = await response.json();
      set({ workspace, isLoading: false });
    } catch (error) {
      console.error('Failed to load workspace:', error);
      set({ isLoading: false });
    }
  },

  addPaper: (paper) => {
    set((state) => ({ papers: [...state.papers, paper] }));
  },

  addArtifact: (artifact) => {
    set((state) => ({ artifacts: [...state.artifacts, artifact] }));
  },
}));
```

**Step 2: Create chat store**

```typescript
// frontend/stores/chat.ts
import { create } from 'zustand';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentSkill: string | null;

  sendMessage: (content: string, skill?: string) => Promise<void>;
  addMessage: (message: Message) => void;
  setCurrentSkill: (skill: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  currentSkill: null,

  sendMessage: async (content: string, skill?: string) => {
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      currentSkill: skill || null,
    }));

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: content,
          skill: skill || null,
        }),
      });

      // Handle SSE stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            if (data.content) {
              assistantContent += data.content;
            }
          }
        }
      }

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: assistantContent,
        created_at: new Date().toISOString(),
      };

      set((state) => ({
        messages: [...state.messages, assistantMessage],
        isStreaming: false,
      }));
    } catch (error) {
      console.error('Failed to send message:', error);
      set({ isStreaming: false });
    }
  },

  addMessage: (message) => {
    set((state) => ({ messages: [...state.messages, message] }));
  },

  setCurrentSkill: (skill) => {
    set({ currentSkill: skill });
  },
}));
```

**Step 3: Commit**

```bash
git add frontend/stores/
git commit -m "feat(frontend): add Zustand stores for workspace and chat"
```

---

### Task 3.2: Create Workbench Page

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/LiteraturePanel.tsx`

**Step 1: Create main page**

```tsx
// frontend/app/(workbench)/workspaces/[id]/page.tsx
'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useWorkspaceStore } from '@/stores/workspace';
import { ChatPanel } from './components/ChatPanel';
import { KnowledgePanel } from './components/KnowledgePanel';
import { LiteraturePanel } from './components/LiteraturePanel';

export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params.id as string;
  const { workspace, loadWorkspace } = useWorkspaceStore();

  useEffect(() => {
    loadWorkspace(workspaceId);
  }, [workspaceId, loadWorkspace]);

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-14 border-b border-white/10 px-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">{workspace?.name || 'Loading...'}</h1>
          {workspace?.type && (
            <span className="px-2 py-1 bg-indigo-500/20 text-indigo-400 text-xs rounded">
              {workspace.type.toUpperCase()}
            </span>
          )}
        </div>
      </header>

      {/* Main content - three columns */}
      <div className="flex-1 flex overflow-hidden">
        <div className="w-64 border-r border-white/10">
          <KnowledgePanel />
        </div>
        <div className="flex-1">
          <ChatPanel />
        </div>
        <div className="w-80 border-l border-white/10">
          <LiteraturePanel />
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Create ChatPanel**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx
'use client';

import { useState } from 'react';
import { useChatStore } from '@/stores/chat';
import { SkillSelector } from './SkillSelector';

export function ChatPanel() {
  const { messages, isStreaming, sendMessage, currentSkill } = useChatStore();
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    sendMessage(input, currentSkill || undefined);
    setInput('');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] p-3 rounded-lg ${
                msg.role === 'user'
                  ? 'bg-indigo-500 text-white'
                  : 'bg-white/10 text-white'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {isStreaming && (
          <div className="flex justify-start">
            <div className="bg-white/10 p-3 rounded-lg">
              <span className="animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
      </div>

      {/* Skill selector */}
      <SkillSelector />

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-white/10">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 bg-white/10 rounded-lg px-4 py-2 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2 bg-indigo-500 text-white rounded-lg disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
```

**Step 3: Create KnowledgePanel and LiteraturePanel**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx
'use client';

import { useWorkspaceStore } from '@/stores/workspace';

export function KnowledgePanel() {
  const { artifacts } = useWorkspaceStore();

  return (
    <div className="h-full p-4">
      <h2 className="text-sm font-semibold text-white/70 mb-4">Knowledge Timeline</h2>
      <div className="space-y-2">
        {artifacts.map((artifact) => (
          <div
            key={artifact.id}
            className="p-3 bg-white/5 rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <div className="text-sm font-medium">{artifact.title || artifact.type}</div>
            <div className="text-xs text-white/50 mt-1">
              {new Date(artifact.created_at).toLocaleDateString()}
            </div>
          </div>
        ))}
        {artifacts.length === 0 && (
          <p className="text-sm text-white/50">No artifacts yet</p>
        )}
      </div>
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/LiteraturePanel.tsx
'use client';

import { useWorkspaceStore } from '@/stores/workspace';

export function LiteraturePanel() {
  const { papers } = useWorkspaceStore();

  return (
    <div className="h-full p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-white/70">Literature</h2>
        <button className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-1 rounded">
          + Upload
        </button>
      </div>
      <div className="space-y-2">
        {papers.map((paper) => (
          <div
            key={paper.id}
            className="p-3 bg-white/5 rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <div className="text-sm font-medium line-clamp-2">{paper.title}</div>
            {paper.year && (
              <div className="text-xs text-white/50 mt-1">{paper.year}</div>
            )}
          </div>
        ))}
        {papers.length === 0 && (
          <p className="text-sm text-white/50">No papers uploaded</p>
        )}
      </div>
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add frontend/app/\(workbench\)/ frontend/stores/
git commit -m "feat(frontend): add workbench page with three-column layout"
```

---

## Phase 4: Authentication System

### Task 4.1: Migrate Auth Service

**Files:**
- Copy: `backend/src/services/auth.py` (from AcademiaGPT)
- Copy: `backend/src/services/user_service.py` (from AcademiaGPT)
- Copy: `backend/src/services/email_service.py` (from AcademiaGPT)

**Step 1: Copy auth service**

```bash
# Copy from original project
cp /home/cjz/AcademiaGPT/backend/services/auth.py /home/cjz/academiagpt-v2/backend/src/services/auth.py
cp /home/cjz/AcademiaGPT/backend/services/user_service.py /home/cjz/academiagpt-v2/backend/src/services/user_service.py
cp /home/cjz/AcademiaGPT/backend/services/email_service.py /home/cjz/academiagpt-v2/backend/src/services/email_service.py
```

**Step 2: Update imports for new project structure**

```python
# Update imports in auth.py
from src.config import settings  # Instead of backend.core.settings

# Update imports in user_service.py
from src.database import get_db  # Instead of backend.database
from src.database.models import User, UserSession  # Instead of backend.database.models
```

**Step 3: Create auth router**

```python
# src/gateway/routers/auth.py
"""Authentication API router."""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.services.auth import create_tokens, verify_access_token
from src.services.user_service import UserService

router = APIRouter()
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token_data = verify_access_token(credentials.credentials)
    if not token_data:
        raise HTTPException(status_code=401, detail="无效或过期的令牌")

    user_service = UserService(db)
    user = await user_service.get_user_by_id(token_data.user_id)

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return user


# Import endpoints from original auth.py
# (login, register, logout, refresh, me, etc.)
```

**Step 4: Commit**

```bash
git add src/services/auth.py src/services/user_service.py src/services/email_service.py src/gateway/routers/auth.py
git commit -m "feat(auth): migrate authentication services from AcademiaGPT v1"
```

---

## Summary

**Phase 1: Lead Agent + Skills**
- Tasks 1.1 - 1.8
- Estimated: 16 tasks

**Phase 2: PDF/Index System**
- Task 2.1 (PDF extraction)
- Add: paper upload endpoint, TOC storage

**Phase 3: Frontend**
- Tasks 3.1 - 3.2
- Add: workspace list page, skill selector component

**Phase 4: Authentication**
- Task 4.1
- Add: auth router integration, tests

---

*Plan created: 2026-03-08*
