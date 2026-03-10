"""Tests for SandboxMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.middlewares.sandbox import SandboxMiddleware
from src.sandbox import Sandbox


class MockSandbox(Sandbox):
    """Mock sandbox for testing."""

    async def execute_command(self, command: str, timeout: int = 300):
        pass

    async def read_file(self, path: str) -> str:
        return ""

    async def write_file(self, path: str, content: str, append: bool = False) -> None:
        pass

    async def list_dir(self, path: str, max_depth: int = 2):
        return []


class TestSandboxMiddleware:
    """Test cases for SandboxMiddleware."""

    @pytest.mark.asyncio
    async def test_before_model_acquires_sandbox(self):
        """Verify that before_model acquires sandbox from provider."""
        # Arrange
        mock_sandbox = MockSandbox(id="test-sandbox-123")
        mock_provider = MagicMock()
        mock_provider.acquire = AsyncMock(return_value=mock_sandbox)

        middleware = SandboxMiddleware(provider=mock_provider)

        state = {"messages": [], "sandbox": None}
        config = {"configurable": {"thread_id": "test-thread-1"}}

        # Act
        result = await middleware.before_model(state, config)

        # Assert
        mock_provider.acquire.assert_awaited_once_with("test-thread-1")
        assert result is not None
        assert "sandbox" in result
        assert result["sandbox"]["sandbox_id"] == "test-sandbox-123"

    @pytest.mark.asyncio
    async def test_before_model_skips_if_sandbox_exists(self):
        """Verify that before_model skips acquisition if sandbox already exists."""
        # Arrange
        mock_provider = MagicMock()
        mock_provider.acquire = AsyncMock()

        middleware = SandboxMiddleware(provider=mock_provider)

        # State already has a sandbox
        state = {"messages": [], "sandbox": {"sandbox_id": "existing-sandbox"}}
        config = {"configurable": {"thread_id": "test-thread-1"}}

        # Act
        result = await middleware.before_model(state, config)

        # Assert
        mock_provider.acquire.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(self):
        """Verify that after_model returns empty dict."""
        # Arrange
        mock_provider = MagicMock()
        middleware = SandboxMiddleware(provider=mock_provider)

        state = {"messages": [], "sandbox": {"sandbox_id": "test-sandbox"}}
        config = {"configurable": {"thread_id": "test-thread-1"}}

        # Act
        result = await middleware.after_model(state, config)

        # Assert
        assert result == {}
