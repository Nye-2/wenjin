"""Tests for workspace-bound memory formatting and injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dataservice.domains.workspace_memory.contracts import WorkspaceMemoryDocumentProjection
from src.dataservice.domains.workspace_memory.service import (
    format_workspace_memory_for_prompt,
    normalize_workspace_memory_content,
)
from src.services.workspace_memory_service import build_workspace_memory_context


class TestFormatWorkspaceMemoryForPrompt:
    def test_empty_document_returns_empty_string(self):
        assert format_workspace_memory_for_prompt(None) == ""

    def test_formats_workspace_memory_document(self):
        document = WorkspaceMemoryDocumentProjection(
            id="memory-1",
            workspace_id="ws-1",
            content_markdown="# Workspace Memory\n\n## Project Context\n- 当前写软著申报材料",
            content_hash="hash",
            revision=1,
            updated_by="system",
        )

        result = format_workspace_memory_for_prompt(document)

        assert "<workspace_memory>" in result
        assert "当前写软著申报材料" in result

    def test_respects_prompt_budget(self):
        document = WorkspaceMemoryDocumentProjection(
            id="memory-1",
            workspace_id="ws-1",
            content_markdown="# Workspace Memory\n" + ("- 很长\n" * 2000),
            content_hash="hash",
            revision=1,
            updated_by="system",
        )

        result = format_workspace_memory_for_prompt(document)

        assert len(result) < 3200
        assert "- ..." in result

    def test_normalizes_empty_memory_to_template(self):
        result = normalize_workspace_memory_content("")
        assert result.startswith("# Workspace Memory")
        assert "## Project Context" in result


class TestBuildWorkspaceMemoryContext:
    @pytest.mark.asyncio
    async def test_returns_empty_without_workspace_id(self):
        assert await build_workspace_memory_context(None) == ""

    @pytest.mark.asyncio
    async def test_formats_loaded_workspace_memory(self):
        dataservice = AsyncMock()
        dataservice.get_workspace_memory_document = AsyncMock(
            return_value=WorkspaceMemoryDocumentProjection(
                id="memory-1",
                workspace_id="ws-1",
                content_markdown="# Workspace Memory\n\n## User Preferences\n- Python 数模代码",
                content_hash="hash",
                revision=1,
                updated_by="system",
            )
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=dataservice)
        context.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.workspace_memory_service.dataservice_client", return_value=context):
            result = await build_workspace_memory_context("ws-1")

        assert "<workspace_memory>" in result
        assert "Python 数模代码" in result
        dataservice.get_workspace_memory_document.assert_awaited_once_with("ws-1")
