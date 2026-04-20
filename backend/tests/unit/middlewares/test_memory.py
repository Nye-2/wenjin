"""Tests for MemoryMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class TestMemoryMiddleware:
    """Test cases for MemoryMiddleware."""

    @pytest.fixture
    def mock_queue(self):
        """Create a mock MemoryQueue."""
        queue = MagicMock()
        queue.enqueue = MagicMock()
        return queue

    @pytest.fixture
    def middleware(self, mock_queue):
        """Create a MemoryMiddleware instance with mock queue."""
        from src.agents.middlewares.memory import MemoryMiddleware
        return MemoryMiddleware(queue=mock_queue, enabled=True)

    @pytest.fixture
    def initial_state(self):
        """Create an initial state with conversation messages."""
        return {
            "messages": [
                HumanMessage(content="Hello, I'm working on machine learning research."),
                AIMessage(content="That's great! How can I help you with your ML research?"),
            ]
        }

    @pytest.fixture
    def config(self):
        """Create a config with thread_id."""
        return {
            "configurable": {
                "thread_id": "test-thread-123",
                "user_id": "user-1",
                "workspace_id": "ws-1",
            }
        }

    @pytest.mark.asyncio
    async def test_before_model_returns_empty(self, middleware, initial_state, config):
        """Verify that before_model returns empty dict."""
        # Act
        result = await middleware.before_model(initial_state, config)

        # Assert
        assert result == {}

    @pytest.mark.asyncio
    async def test_before_model_injects_memory_context(self, middleware, initial_state, config):
        """Verify that before_model injects formatted long-term memory when available."""
        with patch(
            "src.agents.middlewares.memory.build_memory_context",
            return_value="<academic_memory>\n- 偏好 IEEE\n</academic_memory>",
        ):
            result = await middleware.before_model(initial_state, config)

        assert "memory_context" in result
        assert "偏好 IEEE" in result["memory_context"]

    @pytest.mark.asyncio
    async def test_before_model_passes_recent_conversation_context(self, middleware, config):
        """Recent human/final-AI turns should be used to rank injected memory."""
        state = {
            "messages": [
                HumanMessage(content="帮我给 FastAPI 项目设计 pytest 回归测试"),
                AIMessage(content="先确认接口和依赖边界。"),
                AIMessage(
                    content="调用工具中",
                    tool_calls=[{"name": "read_file", "id": "call-1", "args": {}}],
                ),
                ToolMessage(content="tool output", tool_call_id="call-1"),
            ]
        }
        build_memory_context = AsyncMock(return_value="<academic_memory></academic_memory>")

        with patch(
            "src.agents.middlewares.memory.build_memory_context",
            build_memory_context,
        ):
            await middleware.before_model(state, config)

        current_context = build_memory_context.await_args.kwargs["current_context"]
        assert "FastAPI" in current_context
        assert "pytest" in current_context
        assert "调用工具中" not in current_context

    @pytest.mark.asyncio
    async def test_after_model_enqueues_conversation(self, middleware, mock_queue, config):
        """Verify that after_model enqueues messages to the memory queue."""
        # Arrange
        state = {
            "messages": [
                HumanMessage(content="User message 1"),
                AIMessage(content="AI response 1"),
                HumanMessage(content="User message 2"),
                AIMessage(content="AI response 2"),
            ]
        }

        # Act
        result = await middleware.after_model(state, config)

        # Assert
        mock_queue.enqueue.assert_called_once()
        call_args = mock_queue.enqueue.call_args
        assert call_args[0][0] == "test-thread-123"  # thread_id
        # Capture should only enqueue the newest user->assistant delta.
        enqueued_messages = call_args[0][1]
        assert len(enqueued_messages) == 2
        assert enqueued_messages[0].content == "User message 2"
        assert enqueued_messages[1].content == "AI response 2"
        assert "callback" in call_args.kwargs
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_skips_when_disabled(self, mock_queue, config):
        """Verify that after_model skips processing when disabled."""
        # Arrange
        from src.agents.middlewares.memory import MemoryMiddleware
        middleware = MemoryMiddleware(queue=mock_queue, enabled=False)

        state = {
            "messages": [
                HumanMessage(content="User message"),
                AIMessage(content="AI response"),
            ]
        }

        # Act
        result = await middleware.after_model(state, config)

        # Assert
        mock_queue.enqueue.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_skips_short_conversations(self, middleware, mock_queue, config):
        """Verify that after_model skips conversations with fewer than 2 messages."""
        # Arrange - Only one message (too short for meaningful memory)
        state = {
            "messages": [
                HumanMessage(content="Hello"),
            ]
        }

        # Act
        result = await middleware.after_model(state, config)

        # Assert
        mock_queue.enqueue.assert_not_called()
        assert result == {}


class TestFilterMessagesForMemory:
    """Focused tests for memory message filtering."""

    @staticmethod
    def _upload_block() -> str:
        return (
            "<uploaded_files>\n"
            "- file.pdf (1024 bytes): /mnt/user-data/uploads/thread/file.pdf\n"
            "</uploaded_files>"
        )

    def test_upload_only_turn_and_paired_ai_are_dropped(self):
        from src.agents.middlewares.memory import _filter_messages_for_memory

        result = _filter_messages_for_memory(
            [
                HumanMessage(content=self._upload_block()),
                AIMessage(content="I have loaded the uploaded file."),
            ]
        )

        assert result == []

    def test_upload_block_is_removed_but_real_question_is_kept(self):
        from src.agents.middlewares.memory import _filter_messages_for_memory

        result = _filter_messages_for_memory(
            [
                HumanMessage(
                    content=f"{self._upload_block()}\n\n请总结这个文件的关键结论。"
                ),
                AIMessage(content="这个文件主要讨论了实验设计。"),
            ]
        )

        assert len(result) == 2
        assert result[0].content == "请总结这个文件的关键结论。"
        assert "/mnt/user-data/uploads/" not in result[0].content
        assert result[1].content == "这个文件主要讨论了实验设计。"

    def test_tool_messages_and_tool_call_ai_are_excluded(self):
        from src.agents.middlewares.memory import _filter_messages_for_memory

        result = _filter_messages_for_memory(
            [
                HumanMessage(content="帮我检索论文"),
                AIMessage(
                    content="先调用检索工具",
                    tool_calls=[{"name": "search", "id": "call-1", "args": {}}],
                ),
                ToolMessage(content="检索结果", tool_call_id="call-1"),
                AIMessage(content="我已经整理出 3 篇相关论文。"),
            ]
        )

        assert len(result) == 2
        assert result[0].content == "帮我检索论文"
        assert result[1].content == "我已经整理出 3 篇相关论文。"
