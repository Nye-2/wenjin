"""Tests for chat agent tools — one happy-path test per tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.chat_agent.tools import (
    make_cancel_run,
    make_dispatch_capability,
    make_query_run_progress,
    make_read_decisions,
    make_read_documents_meta,
    make_read_library_meta,
    make_read_memory,
    make_read_run_history,
    make_write_decision,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_deps():
    deps = MagicMock()
    deps.workspace_id = "ws-1"
    deps.workspace_type = "thesis"
    deps.user_id = "u-1"

    # All service calls are async
    deps.execution_service.list_executions = AsyncMock(return_value=[])
    deps.execution_service.create_execution = AsyncMock(
        return_value=MagicMock(id="e-1")
    )
    deps.execution_service.get_by_id = AsyncMock(
        return_value=MagicMock(id="e-1", status="running", progress=42)
    )
    deps.execution_service.get_execution_graph = AsyncMock(
        return_value={"nodes": [], "edges": []}
    )
    deps.execution_service.cancel_execution = AsyncMock(
        return_value=MagicMock(id="e-1", status="cancelled")
    )
    deps.capability_resolver.resolve = AsyncMock(return_value=MagicMock())
    deps.decisions_service.get_active = AsyncMock(return_value={})
    deps.decisions_service.set = AsyncMock(
        return_value=MagicMock(id="d-1")
    )
    deps.memory_service.top = AsyncMock(return_value=[])
    deps.run_history_service.list = AsyncMock(return_value=[])
    deps.documents_service.list = AsyncMock(return_value=[])
    deps.library_service.list = AsyncMock(return_value=[])
    return deps


# ---------------------------------------------------------------------------
# 1. dispatch_capability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_capability_creates_execution(mock_deps):
    """Happy path: dispatch returns execution_id."""
    tool = make_dispatch_capability(mock_deps)
    result = await tool.ainvoke(
        {
            "capability_id": "deep_research",
            "brief": {"topic": "GAN"},
            "raw_message": "调研 GAN",
        }
    )
    assert result["execution_id"] == "e-1"
    assert result["capability_id"] == "deep_research"
    assert result["status"] == "dispatched"


@pytest.mark.asyncio
async def test_dispatch_blocked_when_busy(mock_deps):
    """Lead busy: returns error message."""
    active = MagicMock(feature_id="deep_research", progress=50)
    mock_deps.execution_service.list_executions = AsyncMock(return_value=[active])

    tool = make_dispatch_capability(mock_deps)
    result = await tool.ainvoke(
        {
            "capability_id": "outline",
            "brief": {},
            "raw_message": "生成大纲",
        }
    )
    assert result["error"] == "lead_busy"
    assert "进度" in result["message"] or "等" in result["message"]


@pytest.mark.asyncio
async def test_dispatch_unknown_capability(mock_deps):
    """Unknown capability: returns error."""
    mock_deps.capability_resolver.resolve = AsyncMock(
        side_effect=Exception("not found")
    )
    tool = make_dispatch_capability(mock_deps)
    result = await tool.ainvoke(
        {
            "capability_id": "nonexistent",
            "brief": {},
            "raw_message": "do something",
        }
    )
    assert result["error"] == "unknown_capability"


# ---------------------------------------------------------------------------
# 2. query_run_progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_run_progress_returns_graph(mock_deps):
    """Happy path: returns status + node_states."""
    tool = make_query_run_progress(mock_deps)
    result = await tool.ainvoke({"execution_id": "e-1"})
    assert result["execution_id"] == "e-1"
    assert result["status"] == "running"
    assert "node_states" in result


@pytest.mark.asyncio
async def test_query_run_progress_not_found(mock_deps):
    """Execution not found: returns error dict."""
    mock_deps.execution_service.get_by_id = AsyncMock(return_value=None)
    tool = make_query_run_progress(mock_deps)
    result = await tool.ainvoke({"execution_id": "missing"})
    assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# 3. cancel_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_run_returns_cancelled(mock_deps):
    """Happy path: cancel returns status=cancelled."""
    tool = make_cancel_run(mock_deps)
    result = await tool.ainvoke({"execution_id": "e-1"})
    assert result["status"] == "cancelled"
    assert result["execution_id"] == "e-1"


@pytest.mark.asyncio
async def test_cancel_run_not_found(mock_deps):
    """Execution not found: returns error."""
    mock_deps.execution_service.cancel_execution = AsyncMock(return_value=None)
    tool = make_cancel_run(mock_deps)
    result = await tool.ainvoke({"execution_id": "ghost"})
    assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# 4. write_decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_decision_returns_ok(mock_deps):
    """Happy path: write_decision returns status=ok and decision_id."""
    tool = make_write_decision(mock_deps)
    result = await tool.ainvoke({"key": "citation_style", "value": "APA"})
    assert result["status"] == "ok"
    assert result["decision_id"] == "d-1"
    mock_deps.decisions_service.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. read_decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_decisions_returns_dict(mock_deps):
    """Happy path: read_decisions returns decisions dict."""
    mock_deps.decisions_service.get_active = AsyncMock(
        return_value={"citation_style": "APA"}
    )
    tool = make_read_decisions(mock_deps)
    result = await tool.ainvoke({})
    assert result["decisions"] == {"citation_style": "APA"}


# ---------------------------------------------------------------------------
# 6. read_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_memory_returns_facts(mock_deps):
    """Happy path: read_memory returns list of facts."""
    fact = MagicMock(id="f-1", category="user_preferences", content="用APA", confidence=1.0)
    mock_deps.memory_service.top = AsyncMock(return_value=[fact])

    tool = make_read_memory(mock_deps)
    result = await tool.ainvoke({})
    assert len(result["facts"]) == 1
    assert result["facts"][0]["id"] == "f-1"
    assert result["facts"][0]["content"] == "用APA"


@pytest.mark.asyncio
async def test_read_memory_with_category(mock_deps):
    """Category filter is forwarded to memory_service.top."""
    tool = make_read_memory(mock_deps)
    await tool.ainvoke({"category": "preferences", "k": 5})
    mock_deps.memory_service.top.assert_awaited_once_with(
        "ws-1", k=5, category="preferences"
    )


# ---------------------------------------------------------------------------
# 7. read_run_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_run_history_returns_runs(mock_deps):
    """Happy path: read_run_history returns list of runs."""
    run = MagicMock(
        id="r-1",
        execution_id="e-1",
        capability_id="deep_research",
        title="GAN 调研",
        summary="已完成",
        status="completed",
        duration_seconds=120,
    )
    mock_deps.run_history_service.list = AsyncMock(return_value=[run])

    tool = make_read_run_history(mock_deps)
    result = await tool.ainvoke({})
    assert len(result["runs"]) == 1
    assert result["runs"][0]["id"] == "r-1"
    assert result["runs"][0]["capability_id"] == "deep_research"


# ---------------------------------------------------------------------------
# 8. read_documents_meta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_documents_meta_returns_meta(mock_deps):
    """Happy path: read_documents_meta returns document metadata."""
    # MagicMock reserves 'name' kwarg — set it after construction.
    doc = MagicMock(id="doc-1", kind="draft", version=2)
    doc.name = "第一章"
    mock_deps.documents_service.list = AsyncMock(return_value=[doc])

    tool = make_read_documents_meta(mock_deps)
    result = await tool.ainvoke({})
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "doc-1"
    assert result["documents"][0]["name"] == "第一章"
    assert result["documents"][0]["version"] == 2


@pytest.mark.asyncio
async def test_read_documents_meta_kind_filter(mock_deps):
    """kind filter excludes non-matching documents."""
    doc_draft = MagicMock(id="doc-1", kind="draft", version=1)
    doc_draft.name = "Draft"
    doc_outline = MagicMock(id="doc-2", kind="outline", version=1)
    doc_outline.name = "Outline"
    mock_deps.documents_service.list = AsyncMock(return_value=[doc_draft, doc_outline])

    tool = make_read_documents_meta(mock_deps)
    result = await tool.ainvoke({"kind": "outline"})
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "doc-2"


# ---------------------------------------------------------------------------
# 9. read_library_meta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_library_meta_returns_items(mock_deps):
    """Happy path: read_library_meta returns library item metadata."""
    item = MagicMock(id="lib-1", title="Deep Learning", year=2016, item_type="paper")
    mock_deps.library_service.list = AsyncMock(return_value=[item])

    tool = make_read_library_meta(mock_deps)
    result = await tool.ainvoke({})
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "lib-1"
    assert result["items"][0]["title"] == "Deep Learning"
    assert result["items"][0]["year"] == 2016


@pytest.mark.asyncio
async def test_read_library_meta_item_type_filter(mock_deps):
    """item_type filter excludes non-matching items."""
    paper = MagicMock(id="lib-1", title="A Paper", year=2020, item_type="paper")
    book = MagicMock(id="lib-2", title="A Book", year=2019, item_type="book")
    mock_deps.library_service.list = AsyncMock(return_value=[paper, book])

    tool = make_read_library_meta(mock_deps)
    result = await tool.ainvoke({"item_type": "book"})
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "lib-2"
