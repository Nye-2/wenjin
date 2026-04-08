"""Tests for chat_turn_handler – agent-level timeout."""

import asyncio
from types import SimpleNamespace

import pytest
from langgraph.errors import GraphRecursionError
from unittest.mock import AsyncMock, patch, MagicMock

from src.application.errors import ApplicationError
from src.application.handlers.chat_turn_handler import ChatStreamDelta, ChatTurnHandler
from src.application.results import PreparedChatTurn
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
    async def test_agent_graph_recursion_returns_fallback_reply(self):
        """Graph recursion should degrade to a deterministic fallback reply."""
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=GraphRecursionError("loop"))

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
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.chat_turn_handler import generate_chat_response

            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.message = "请帮我开始功能"
            mock_request.attachments = ()
            mock_request.metadata = {
                "orchestration": {"feature_id": "framework_outline"}
            }

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = None
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = []

            reply = await generate_chat_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert "重复工具调用" in reply.content
            assert reply.metadata.get("guard") == "graph_recursion_fallback"


class TestChatTurnHandlerCancellation:
    """Cancellation should still settle thread status and refunds."""

    @pytest.mark.asyncio
    async def test_complete_turn_marks_thread_failed_when_cancelled(self):
        handler = ChatTurnHandler(chat_thread_service=MagicMock())
        request = MagicMock()
        request.message = "hello"
        thread = MagicMock()
        prepared = PreparedChatTurn(request=request, thread=thread)

        handler._generate_chat_response = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        handler._refund_chat_turn_billing = AsyncMock()
        handler._fail_chat_turn = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await handler.complete_turn(prepared, actor_id="user-1")

        handler._refund_chat_turn_billing.assert_not_awaited()
        handler._fail_chat_turn.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_stream_chat_response_yields_incremental_chunks_and_final_reply(self):
        stream_result = {
            "messages": [
                SimpleNamespace(
                    content="hello world",
                    additional_kwargs={
                        "reasoning": {
                            "summary": [
                                {"type": "summary_text", "text": "reasoning summary"}
                            ]
                        }
                    },
                )
            ],
            "response_blocks": [],
            "response_metadata": {},
        }

        class _FakeAgentStreamRun:
            async def _iterate(self):
                yield (
                    "messages",
                    (
                        SimpleNamespace(
                            content="hello ",
                            additional_kwargs={
                                "reasoning": {
                                    "summary": [
                                        {"type": "summary_text", "text": "think "}
                                    ]
                                }
                            },
                        ),
                        {"langgraph_node": "agent"},
                    ),
                )
                yield (
                    "messages",
                    (
                        SimpleNamespace(content="world"),
                        {"langgraph_node": "agent"},
                    ),
                )
                yield ("values", stream_result)

            def __aiter__(self):
                return self._iterate()

            async def result(self):
                return stream_result

        class _FakeStreamingAgent:
            def astream_with_result(self, *args, **kwargs):
                return _FakeAgentStreamRun()

        with (
            patch(
                "src.agents.lead_agent.agent.make_lead_agent",
                return_value=_FakeStreamingAgent(),
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
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.chat_turn_handler.get_model_config",
                return_value=SimpleNamespace(model="test-model", supports_streaming=True),
            ),
            patch(
                "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.chat_turn_handler import stream_chat_response

            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.message = "hello"
            mock_request.attachments = ()
            mock_request.metadata = None

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = None
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = []

            stream = stream_chat_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )
            chunks = [chunk async for chunk in stream]
            reply = await stream.wait_reply()

            assert chunks == [
                ChatStreamDelta(kind="reasoning", text="think"),
                ChatStreamDelta(kind="content", text="hello "),
                ChatStreamDelta(kind="content", text="world"),
            ]
            assert reply.content == "hello world"
            assert reply.blocks[0]["type"] == "reasoning"
            assert reply.blocks[0]["data"]["text"] == "reasoning summary"

    @pytest.mark.asyncio
    async def test_generate_chat_response_extracts_reasoning_into_blocks(self):
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    SimpleNamespace(
                        content="final answer",
                        additional_kwargs={
                            "reasoning": {
                                "summary": [
                                    {"type": "summary_text", "text": "step 1\nstep 2"}
                                ]
                            }
                        },
                    )
                ],
                "response_blocks": [],
                "response_metadata": {},
            }
        )

        with (
            patch(
                "src.agents.lead_agent.agent.make_lead_agent",
                return_value=fake_agent,
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
                "src.application.handlers.chat_turn_handler.route_chat_model",
                return_value="minimax-m2.7",
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
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.chat_turn_handler import generate_chat_response

            mock_request = MagicMock()
            mock_request.model = "minimax-m2.7"
            mock_request.message = "hello"
            mock_request.attachments = ()
            mock_request.metadata = None

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = None
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = []

            reply = await generate_chat_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert reply.content == "final answer"
            assert reply.blocks[0]["type"] == "reasoning"
            assert "step 1" in reply.blocks[0]["data"]["text"]

    @pytest.mark.asyncio
    async def test_generate_chat_response_exposes_explicit_orchestration_metadata_to_agent(self):
        """Structured orchestration metadata should become agent-visible context instead of direct execution."""
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [SimpleNamespace(content="agent answer")],
                "response_blocks": [],
                "response_metadata": {},
            }
        )

        with (
            patch(
                "src.agents.lead_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.agents.lead_agent.agent.make_lead_agent",
                return_value=fake_agent,
            ),
            patch(
                "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.application.handlers.chat_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.chat_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.chat_turn_handler import generate_chat_response

            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.message = "请帮我开始「框架与摘要」。"
            mock_request.attachments = ()
            mock_request.metadata = {
                "orchestration": {
                    "feature_id": "framework_outline",
                    "params": {
                        "paper_title": "Agent Systems",
                        "topic": "LLM planning",
                    },
                }
            }

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = None
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = [
                {
                    "role": "user",
                    "content": "请帮我开始「框架与摘要」。",
                    "metadata": {
                        "orchestration": {
                            "feature_id": "framework_outline",
                            "params": {
                                "paper_title": "Agent Systems",
                                "topic": "LLM planning",
                            },
                        }
                    },
                }
            ]

            reply = await generate_chat_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert reply.content == "agent answer"
            invoked_state = fake_agent.ainvoke.await_args.args[0]
            rendered_message = invoked_state["messages"][0].content
            assert "请帮我开始「框架与摘要」。" in rendered_message
            assert "<workspace_feature_seed>" in rendered_message
            assert "feature_id: framework_outline" in rendered_message
            assert "paper_title" in rendered_message
            assert "LLM planning" in rendered_message

    @pytest.mark.asyncio
    async def test_generate_chat_response_skips_pre_bridge_for_freeform_chat(self):
        """Free-form chat should stay on the agent path instead of pre-bridging features."""
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [SimpleNamespace(content="agent answer")],
                "response_blocks": [],
                "response_metadata": {},
            }
        )

        with (
            patch(
                "src.agents.lead_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.agents.lead_agent.agent.make_lead_agent",
                return_value=fake_agent,
            ),
            patch(
                "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
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
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.chat_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.chat_turn_handler import generate_chat_response

            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.message = "如何做实验设计？"
            mock_request.attachments = ()
            mock_request.metadata = None

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = "framework-designer"
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = []

            reply = await generate_chat_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert reply.content == "agent answer"
            fake_agent.ainvoke.assert_awaited_once()

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
