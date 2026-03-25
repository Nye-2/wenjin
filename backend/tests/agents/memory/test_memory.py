"""Tests for canonical long-term memory formatting and injection."""

from unittest.mock import AsyncMock, patch

import pytest

from src.config.config_loader import MemoryConfig
from src.services.user_memory_service import build_memory_context, format_knowledge_for_prompt


class TestFormatKnowledgeForPrompt:
    def test_empty_items_return_empty_string(self):
        assert format_knowledge_for_prompt([]) == ""

    def test_formats_memory_by_category(self):
        items = [
            {"category": "preference", "content": "偏好 IEEE 引用格式", "confidence": 0.9},
            {"category": "context", "content": "当前研究 Transformer 压缩", "confidence": 0.8},
            {"category": "goal", "content": "完成 SCI 初稿", "confidence": 0.95},
        ]

        result = format_knowledge_for_prompt(items)

        assert "<academic_memory>" in result
        assert "用户偏好" in result
        assert "研究上下文" in result
        assert "研究目标" in result
        assert "偏好 IEEE 引用格式" in result

    def test_respects_max_chars_budget(self):
        items = [
            {"category": "preference", "content": "偏好 IEEE 引用格式", "confidence": 0.9},
            {"category": "context", "content": "当前研究 Transformer 压缩", "confidence": 0.8},
            {"category": "goal", "content": "完成 SCI 初稿", "confidence": 0.95},
        ]

        result = format_knowledge_for_prompt(items, max_chars=60)

        assert "<academic_memory>" in result
        assert "- ..." in result


class TestBuildMemoryContext:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self):
        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=MemoryConfig(enabled=False),
        ):
            result = await build_memory_context("user-1", "ws-1")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_without_user_id(self):
        result = await build_memory_context(None, "ws-1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_formats_loaded_memory(self):
        config = MemoryConfig(
            enabled=True,
            injection_enabled=True,
            max_injection_tokens=128,
        )
        items = [
            {
                "category": "preference",
                "content": "偏好正式学术语气",
                "confidence": 0.9,
                "workspace_context": "ws-1",
            },
            {
                "category": "context",
                "content": "当前在写 LLM 论文综述",
                "confidence": 0.85,
                "workspace_context": "ws-1",
            },
        ]

        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=config,
        ), patch(
            "src.services.user_memory_service.load_user_memory",
            AsyncMock(return_value=items),
        ):
            result = await build_memory_context("user-1", "ws-1")

        assert "<academic_memory>" in result
        assert "偏好正式学术语气" in result
        assert "当前在写 LLM 论文综述" in result
