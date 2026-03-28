"""Tests for chat_turn_handler – agent-level timeout."""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.application.errors import ApplicationError
from src.config.llm_config import LLMSettings


class TestAgentTimeout:
    """Verify that agent.ainvoke() is bounded by AGENT_TIMEOUT."""

    @pytest.mark.asyncio
    async def test_agent_timeout_raises_application_error(self):
        """Agent hanging beyond AGENT_TIMEOUT should raise ApplicationError."""
        original = LLMSettings.AGENT_TIMEOUT
        LLMSettings.AGENT_TIMEOUT = 0.1  # 100ms for fast test

        try:
            # Create a mock agent that hangs forever
            mock_agent = MagicMock()

            async def slow_invoke(*args, **kwargs):
                await asyncio.sleep(10)
                return {}

            mock_agent.ainvoke = slow_invoke

            with (
                patch(
                    "src.agents.lead_agent.agent.make_lead_agent",
                    return_value=mock_agent,
                ),
                patch(
                    "src.agents.lead_agent.agent.build_pipeline",
                    return_value=[],
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.route_chat_model",
                    return_value="test-model",
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.build_chat_runtime_config",
                    return_value={"configurable": {}},
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.build_chat_initial_state",
                    return_value={},
                ),
                patch(
                    "src.application.handlers.chat_turn_handler._resolve_workspace_id",
                    return_value=None,
                ),
            ):
                from src.application.handlers.chat_turn_handler import (
                    generate_chat_response,
                )

                mock_request = MagicMock()
                mock_request.model = "test-model"
                mock_request.message = "hello"
                mock_request.attachments = ()

                mock_thread = MagicMock()
                mock_thread.id = "thread-1"
                mock_thread.skill = None
                mock_thread.model = None
                mock_thread.workspace_id = None

                with pytest.raises(ApplicationError, match="超时"):
                    await generate_chat_response(
                        mock_request,
                        mock_thread,
                        actor_id="user-1",
                    )
        finally:
            LLMSettings.AGENT_TIMEOUT = original

    @pytest.mark.asyncio
    async def test_agent_completes_within_timeout(self):
        """Agent completing within AGENT_TIMEOUT should return normally."""
        original = LLMSettings.AGENT_TIMEOUT
        LLMSettings.AGENT_TIMEOUT = 5.0  # generous timeout

        try:
            mock_agent = MagicMock()

            async def fast_invoke(*args, **kwargs):
                return {"messages": [], "response_blocks": [], "response_metadata": {}}

            mock_agent.ainvoke = fast_invoke

            with (
                patch(
                    "src.agents.lead_agent.agent.make_lead_agent",
                    return_value=mock_agent,
                ),
                patch(
                    "src.agents.lead_agent.agent.build_pipeline",
                    return_value=[],
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.route_chat_model",
                    return_value="test-model",
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.build_chat_runtime_config",
                    return_value={"configurable": {}},
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.build_chat_initial_state",
                    return_value={},
                ),
                patch(
                    "src.application.handlers.chat_turn_handler._resolve_workspace_id",
                    return_value=None,
                ),
                patch(
                    "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                    return_value=None,
                ),
            ):
                from src.application.handlers.chat_turn_handler import (
                    generate_chat_response,
                )

                mock_request = MagicMock()
                mock_request.model = "test-model"
                mock_request.message = "hello"
                mock_request.attachments = ()

                mock_thread = MagicMock()
                mock_thread.id = "thread-1"
                mock_thread.skill = None
                mock_thread.model = None
                mock_thread.workspace_id = None

                reply = await generate_chat_response(
                    mock_request,
                    mock_thread,
                    actor_id="user-1",
                )
                # Should return a GeneratedChatReply without raising
                assert reply is not None
        finally:
            LLMSettings.AGENT_TIMEOUT = original
