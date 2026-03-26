"""Tests for AcademicMemoryMiddleware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.memory import (
    _filter_messages_for_memory,
    _parse_knowledge_json,
    enqueue_memory_capture,
    extract_and_persist_knowledge,
    format_knowledge_for_prompt,
    load_user_memory,
    messages_to_conversation_text,
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

    def test_messages_to_conversation_text_strips_uploaded_file_markup(self):
        text = messages_to_conversation_text(
            [
                HumanMessage(
                    content=(
                        "<uploaded_files>\n"
                        "- file.txt (12 bytes): /mnt/user-data/uploads/thread/file.txt\n"
                        "</uploaded_files>\n\n"
                        "请提炼这份材料的结论。"
                    )
                ),
                AIMessage(content="核心结论是实验指标有提升。"),
            ]
        )

        assert "/mnt/user-data/uploads/" not in text
        assert "<uploaded_files>" not in text
        assert "user: 请提炼这份材料的结论。" in text
        assert "assistant: 核心结论是实验指标有提升。" in text

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

    def test_enqueue_memory_capture_registers_callback(self):
        queue = MagicMock()
        enqueue_memory_capture(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            messages=[{"role": "user", "content": "hello"}],
            queue=queue,
        )
        queue.enqueue.assert_called_once()
        assert "callback" in queue.enqueue.call_args.kwargs


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

        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=SimpleNamespace(
                enabled=True,
                fact_confidence_threshold=0.7,
                max_facts=100,
            ),
        ):
            count = await extract_and_persist_knowledge("user1", "conversation")

        # At least one valid item should be persisted even if another has bad confidence.
        assert count >= 1
        assert service.upsert.await_count >= 1
        persisted_contents = [call.args[2] for call in service.upsert.await_args_list]
        assert "完成论文" in persisted_contents
