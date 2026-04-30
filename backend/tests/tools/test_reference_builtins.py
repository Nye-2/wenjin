"""Tests for workspace Reference Library built-in tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtins.references import (
    list_workspace_reference_outline_tool,
    read_workspace_reference_section_tool,
    search_workspace_references_tool,
)


@pytest.mark.asyncio
async def test_list_workspace_reference_outline_tool_returns_summary() -> None:
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
        result = await list_workspace_reference_outline_tool.ainvoke(
            {"workspace_id": "ws-1"},
        )

    assert "文献库概览" in result
    index_service.get_workspace_toc_summary.assert_awaited_once_with("ws-1")


@pytest.mark.asyncio
async def test_search_workspace_references_tool_serializes_results() -> None:
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
        result = await search_workspace_references_tool.ainvoke(
            {"workspace_id": "ws-1", "query": "intro", "limit": 5},
        )

    assert "\"count\": 1" in result
    assert "important snippet" in result
    index_service.search_workspace_sections.assert_awaited_once_with("ws-1", "intro", limit=5)


@pytest.mark.asyncio
async def test_read_workspace_reference_section_tool_reads_by_title() -> None:
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
        result = await read_workspace_reference_section_tool.ainvoke(
            {"workspace_id": "ws-1", "reference_id": "reference-1", "section_title": "Method"},
        )

    assert result.startswith("## Method")
    assert "Section body" in result
    index_service.get_reference_section_by_title.assert_awaited_once_with(
        reference_id="reference-1",
        section_title="Method",
        workspace_id="ws-1",
    )


@pytest.mark.asyncio
async def test_read_workspace_reference_section_tool_requires_workspace_context() -> None:
    result = await read_workspace_reference_section_tool.ainvoke(
        {"reference_id": "reference-1", "section_title": "Method"}
    )

    assert "workspace runtime context" in result
