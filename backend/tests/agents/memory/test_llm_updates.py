"""Tests for canonical LLM-driven user-memory persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.config.config_loader import MemoryConfig
from src.services.user_memory_service import (
    KNOWLEDGE_EXTRACTION_PROMPT,
    extract_and_persist_knowledge,
)


class TestKnowledgeExtractionPrompt:
    def test_prompt_exists(self):
        assert KNOWLEDGE_EXTRACTION_PROMPT
        assert "category" in KNOWLEDGE_EXTRACTION_PROMPT
        assert "JSON" in KNOWLEDGE_EXTRACTION_PROMPT


class TestLLMKnowledgeUpdates:
    @pytest.mark.asyncio
    async def test_extract_skips_when_disabled(self):
        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=MemoryConfig(enabled=False),
        ):
            count = await extract_and_persist_knowledge("user-1", "conversation")

        assert count == 0

    @pytest.mark.asyncio
    async def test_extract_persists_only_valid_items(self):
        config = MemoryConfig(enabled=True, fact_confidence_threshold=0.7)

        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=config,
        ), patch(
            "src.models.router.route_model",
            return_value="default",
        ), patch(
            "src.models.factory.create_chat_model",
        ) as mock_model_factory, patch(
            "src.database.get_db_session",
        ) as mock_session, patch(
            "src.services.knowledge_service.KnowledgeService",
        ) as mock_knowledge_service, patch(
            "src.services.user_memory_service._maybe_compact_memory",
            AsyncMock(),
        ) as mock_compact:
            model = mock_model_factory.return_value
            model.ainvoke = AsyncMock(
                return_value=SimpleNamespace(
                    content=(
                        "["
                        '{"category":"preference","content":"偏好 APA","confidence":0.82},'
                        '{"category":"goal","content":"完成论文终稿","confidence":0.91},'
                        '{"category":"unknown","content":"无效分类","confidence":0.99},'
                        '{"category":"context","content":"低置信度内容","confidence":0.3}'
                        "]"
                    )
                )
            )

            mock_db = mock_session.return_value.__aenter__.return_value
            mock_db.commit = AsyncMock()
            service = mock_knowledge_service.return_value
            service.upsert = AsyncMock()

            count = await extract_and_persist_knowledge(
                "user-1",
                "user: 我偏好 APA，并希望本周完成论文终稿",
                workspace_context="ws-1",
                source="test",
            )

        assert count == 2
        assert service.upsert.await_count == 2
        persisted_contents = [call.args[2] for call in service.upsert.await_args_list]
        assert "偏好 APA" in persisted_contents
        assert "完成论文终稿" in persisted_contents
        mock_db.commit.assert_awaited_once()
        mock_compact.assert_awaited_once_with("user-1", workspace_context="ws-1")

    @pytest.mark.asyncio
    async def test_extract_returns_zero_on_invalid_json(self):
        config = MemoryConfig(enabled=True, fact_confidence_threshold=0.7)

        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=config,
        ), patch(
            "src.models.router.route_model",
            return_value="default",
        ), patch(
            "src.models.factory.create_chat_model",
        ) as mock_model_factory:
            model = mock_model_factory.return_value
            model.ainvoke = AsyncMock(return_value=SimpleNamespace(content="not-json"))

            count = await extract_and_persist_knowledge("user-1", "conversation")

        assert count == 0
