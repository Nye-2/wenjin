"""Tests for workspace Reference Library built-in tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtins.references import (
    list_reference_library_tool,
    read_reference_outline_node_tool,
    search_reference_text_units_tool,
)


@pytest.mark.asyncio
async def test_list_reference_library_tool_returns_summary() -> None:
    db = MagicMock()
    index_service = MagicMock()
    index_service.get_workspace_toc_summary = AsyncMock(return_value="## 文献库概览")

    @asynccontextmanager
    async def _db_session():
        yield db

    with (
        patch("src.tools.builtins.references.get_db_session", _db_session),
        patch("src.tools.builtins.references.ReferenceIndexService", return_value=index_service),
    ):
        result = await list_reference_library_tool.ainvoke(
            {},
            config={"configurable": {"workspace_id": "ws-1"}},
        )

    assert "文献库概览" in result
    index_service.get_workspace_toc_summary.assert_awaited_once_with("ws-1")


@pytest.mark.asyncio
async def test_list_reference_library_rejects_workspace_mismatch() -> None:
    result = await list_reference_library_tool.ainvoke(
        {"workspace_id": "ws-other"},
        config={"configurable": {"workspace_id": "ws-runtime"}},
    )

    assert "workspace_scope_violation" in result
    assert "ws-runtime" in result
    assert "ws-other" in result


@pytest.mark.asyncio
async def test_search_reference_text_units_tool_serializes_results() -> None:
    db = MagicMock()
    index_service = MagicMock()
    index_service.search_workspace_sections = AsyncMock(
        return_value=[
            {
                "reference_id": "reference-1",
                "reference_title": "Test Reference",
                "section_path": "1",
                "section_title": "Intro",
                "snippet": "important snippet",
                "level": 1,
                "page_start": 1,
                "page_end": 2,
            }
        ]
    )

    @asynccontextmanager
    async def _db_session():
        yield db

    with (
        patch("src.tools.builtins.references.get_db_session", _db_session),
        patch("src.tools.builtins.references.ReferenceIndexService", return_value=index_service),
    ):
        result = await search_reference_text_units_tool.ainvoke(
            {"query": "intro", "limit": 5},
            config={"configurable": {"workspace_id": "ws-1"}},
        )

    assert "\"count\": 1" in result
    assert "important snippet" in result
    index_service.search_workspace_sections.assert_awaited_once_with("ws-1", "intro", limit=5)


@pytest.mark.asyncio
async def test_read_reference_outline_node_tool_reads_by_title() -> None:
    db = MagicMock()
    index_service = MagicMock()
    index_service.get_reference_section_by_title = AsyncMock(
        return_value={"title": "Method", "content": "Section body"}
    )

    @asynccontextmanager
    async def _db_session():
        yield db

    with (
        patch("src.tools.builtins.references.get_db_session", _db_session),
        patch("src.tools.builtins.references.ReferenceIndexService", return_value=index_service),
    ):
        result = await read_reference_outline_node_tool.ainvoke(
            {"reference_id": "reference-1", "section_title": "Method"},
            config={"configurable": {"workspace_id": "ws-1"}},
        )

    assert result.startswith("## Method")
    assert "Section body" in result
    index_service.get_reference_section_by_title.assert_awaited_once_with(
        reference_id="reference-1",
        section_title="Method",
        workspace_id="ws-1",
    )


@pytest.mark.asyncio
async def test_read_reference_outline_node_records_access_usage() -> None:
    db = MagicMock()
    index_service = MagicMock()
    index_service.get_reference_section_by_title = AsyncMock(
        return_value={
            "node_id": "node-1",
            "title": "Method",
            "content": "Section body",
            "units": [{"id": "unit-1"}],
        }
    )
    usage_service = MagicMock()
    usage_service.record_usage = AsyncMock(return_value={"recorded": 1})

    @asynccontextmanager
    async def _db_session():
        yield db

    with (
        patch("src.tools.builtins.references.get_db_session", _db_session),
        patch("src.tools.builtins.references.ReferenceIndexService", return_value=index_service),
        patch("src.tools.builtins.references.ReferenceUsageService", return_value=usage_service),
    ):
        result = await read_reference_outline_node_tool.ainvoke(
            {"reference_id": "reference-1", "section_title": "Method"},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "execution_id": "exec-1",
                    "task_id": "task-1",
                }
            },
        )

    assert "Section body" in result
    usage_service.record_usage.assert_awaited_once()
    kwargs = usage_service.record_usage.await_args.kwargs
    assert kwargs["workspace_id"] == "ws-1"
    assert kwargs["reference_ids"] == ["reference-1"]
    assert kwargs["outline_node_id"] == "node-1"
    assert kwargs["text_unit_id"] == "unit-1"
    assert kwargs["mark_used_in_draft"] is False


@pytest.mark.asyncio
async def test_read_reference_outline_node_tool_requires_workspace_context() -> None:
    result = await read_reference_outline_node_tool.ainvoke(
        {"reference_id": "reference-1", "section_title": "Method"}
    )

    assert "workspace runtime context" in result


@pytest.mark.asyncio
async def test_reference_tools_do_not_trust_explicit_workspace_without_runtime() -> None:
    result = await list_reference_library_tool.ainvoke(
        {"workspace_id": "ws-explicit"},
    )

    assert "runtime_context_missing" in result
