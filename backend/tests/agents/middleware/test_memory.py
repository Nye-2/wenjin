"""Tests for AcademicMemoryMiddleware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.agents.middlewares.memory import (
    _parse_knowledge_json,
    extract_and_persist_knowledge,
    format_knowledge_for_prompt,
    load_user_memory,
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
        text = (
            '```json\n'
            '[{"category": "context", "content": "NLP", "confidence": 0.8}]\n'
            '```'
        )
        result = _parse_knowledge_json(text)
        assert len(result) == 1

    def test_returns_empty_on_invalid(self):
        assert _parse_knowledge_json("not json") == []

    def test_returns_empty_on_dict(self):
        assert _parse_knowledge_json('{"key": "value"}') == []


class TestLoadUserMemory:
    @patch("src.database.get_db_session")
    async def test_returns_empty_on_error(self, mock_session):
        mock_session.side_effect = Exception("DB error")
        result = await load_user_memory("user1")
        assert result == []


class TestExtractAndPersistKnowledge:
    @patch("src.models.factory.create_chat_model")
    @patch("src.database.get_db_session")
    async def test_returns_zero_on_llm_failure(self, mock_session, mock_model):
        mock_model.side_effect = Exception("LLM unavailable")
        count = await extract_and_persist_knowledge("user1", "some text")
        assert count == 0

    @patch("src.services.knowledge_service.KnowledgeService")
    @patch("src.models.factory.create_chat_model")
    @patch("src.database.get_db_session")
    async def test_invalid_confidence_does_not_abort_all_items(
        self,
        mock_session,
        mock_model,
        mock_knowledge_service,
    ):
        mock_db = mock_session.return_value.__aenter__.return_value
        mock_db.commit = AsyncMock()

        model = mock_model.return_value
        model.ainvoke = AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '[{"category":"preference","content":"偏好APA","confidence":"bad"},'
                    '{"category":"goal","content":"完成论文","confidence":0.9}]'
                )
            )
        )

        service = mock_knowledge_service.return_value
        service.upsert = AsyncMock()

        count = await extract_and_persist_knowledge("user1", "conversation")

        # At least one valid item should be persisted even if another has bad confidence.
        assert count >= 1
        assert service.upsert.await_count >= 1
        persisted_contents = [call.args[2] for call in service.upsert.await_args_list]
        assert "完成论文" in persisted_contents
