"""Tests for MemoryMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


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
        return {"configurable": {"thread_id": "test-thread-123"}}

    @pytest.mark.asyncio
    async def test_before_model_returns_empty(self, middleware, initial_state, config):
        """Verify that before_model returns empty dict."""
        # Act
        result = await middleware.before_model(initial_state, config)

        # Assert
        assert result == {}

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
        # Messages should be filtered (only Human and AI messages)
        enqueued_messages = call_args[0][1]
        assert len(enqueued_messages) == 4
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
