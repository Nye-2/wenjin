"""Tests for workspace-bound memory middleware/runtime helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.memory import (
    _filter_messages_for_memory,
    messages_to_conversation_text,
)
from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryDocumentProjection,
)
from src.dataservice.domains.workspace_memory.service import format_workspace_memory_for_prompt
from src.services.workspace_memory_service import build_workspace_memory_context


class TestWorkspaceMemoryPrompt:
    def test_empty_document_returns_empty_string(self):
        assert format_workspace_memory_for_prompt(None) == ""

    def test_formats_workspace_memory_document(self):
        document = WorkspaceMemoryDocumentProjection(
            id="memory-1",
            workspace_id="ws-1",
            content_markdown="# Workspace Memory\n\n## Project Context\n- 数模论文写作",
            content_hash="hash",
            revision=1,
            updated_by="system",
        )

        result = format_workspace_memory_for_prompt(document)

        assert result.startswith("<workspace_memory>")
        assert "数模论文写作" in result
        assert result.endswith("</workspace_memory>")


class TestMessageSerialization:
    def test_messages_to_conversation_text_ignores_empty_items(self):
        text = messages_to_conversation_text(
            [
                {"role": "user", "content": "请帮我写论文"},
                {"role": "assistant", "content": "可以，先确定题目"},
                {"role": "assistant", "content": "   "},
            ]
        )
        assert "user: 请帮我写论文" in text
        assert "assistant: 可以，先确定题目" in text

    def test_filter_messages_for_memory_skips_upload_only_turn(self):
        filtered = _filter_messages_for_memory(
            [
                HumanMessage(
                    content=(
                        "<uploaded_files>\n"
                        "- appendix.pdf (32 bytes): /mnt/user-data/uploads/thread/appendix.pdf\n"
                        "</uploaded_files>"
                    )
                ),
                AIMessage(content="已读取上传内容。"),
                HumanMessage(content="接着帮我写引言。"),
                AIMessage(content="可以，先明确研究问题。"),
            ]
        )

        assert len(filtered) == 2
        assert filtered[0].content == "接着帮我写引言。"
        assert filtered[1].content == "可以，先明确研究问题。"


class TestBuildWorkspaceMemoryContext:
    @pytest.mark.asyncio
    async def test_returns_empty_without_workspace(self):
        assert await build_workspace_memory_context(None) == ""

    @pytest.mark.asyncio
    async def test_loads_workspace_memory_document(self):
        dataservice = AsyncMock()
        dataservice.get_workspace_memory_document = AsyncMock(
            return_value=WorkspaceMemoryDocumentProjection(
                id="memory-1",
                workspace_id="ws-1",
                content_markdown="# Workspace Memory\n\n## Project Context\n- 软著申报",
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
        assert "软著申报" in result
        dataservice.get_workspace_memory_document.assert_awaited_once_with("ws-1")
