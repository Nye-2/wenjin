"""Tests for thread_turn_handler – agent-level timeout."""

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from src.application.errors import ApplicationError, BadRequestError, PaymentRequiredError
from src.application.handlers.thread_turn_handler import (
    ThreadStreamDelta,
    ThreadTurnHandler,
    _reply_from_agent_result,
    build_thread_initial_state,
)
from src.application.results import (
    PreparedThreadTurn,
    ThreadTurnAttachment,
    ThreadTurnRequest,
)
from src.config.llm_config import LLMSettings


def test_build_thread_initial_state_skips_oversized_image_attachment(tmp_path):
    thread_id = "thread-oversized"
    thread_root = tmp_path / thread_id
    uploads_dir = thread_root / "uploads"
    uploads_dir.mkdir(parents=True)
    oversized_path = uploads_dir / "large.png"
    oversized_path.write_bytes(b"x" * (5 * 1024 * 1024 + 1))

    attachment = ThreadTurnAttachment(
        name="large.png",
        path="/mnt/user-data/uploads/large.png",
        content_type="image/png",
        size_bytes=oversized_path.stat().st_size,
    )
    thread = SimpleNamespace(id=thread_id, messages=[], workspace_id=None, skill=None)

    with patch(
        "src.application.handlers.thread_turn_handler.get_thread_data_root",
        return_value=thread_root,
    ):
        state = build_thread_initial_state(
            thread,
            actor_id="user-1",
            workspace_id=None,
            effective_skill=None,
            attachments=(attachment,),
        )

    assert "uploaded_files" in state
    assert "viewed_images" not in state


def test_build_thread_initial_state_includes_small_image_attachment(tmp_path):
    thread_id = "thread-small"
    thread_root = tmp_path / thread_id
    uploads_dir = thread_root / "uploads"
    uploads_dir.mkdir(parents=True)
    image_path = uploads_dir / "small.png"
    image_bytes = b"\x89PNG\r\n\x1a\nsmall"
    image_path.write_bytes(image_bytes)

    attachment = ThreadTurnAttachment(
        name="small.png",
        path="/mnt/user-data/uploads/small.png",
        content_type="image/png",
        size_bytes=len(image_bytes),
    )
    thread = SimpleNamespace(id=thread_id, messages=[], workspace_id=None, skill=None)

    with patch(
        "src.application.handlers.thread_turn_handler.get_thread_data_root",
        return_value=thread_root,
    ):
        state = build_thread_initial_state(
            thread,
            actor_id="user-1",
            workspace_id=None,
            effective_skill=None,
            attachments=(attachment,),
        )

    assert "viewed_images" in state
    viewed_images = state["viewed_images"]
    assert viewed_images["/mnt/user-data/uploads/small.png"]["mime_type"] == "image/png"
    assert viewed_images["/mnt/user-data/uploads/small.png"]["base64"] == base64.b64encode(image_bytes).decode(
        "utf-8"
    )


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
                    "src.agents.chat_agent.agent.make_chat_agent",
                    return_value=mock_agent,
                ),
                patch(
                    "src.agents.chat_agent.agent.build_pipeline",
                    return_value=[],
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.route_chat_model",
                    return_value="test-model",
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                    return_value={"configurable": {}},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                    return_value={},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                    return_value=None,
                ),
            ):
                from src.application.handlers.thread_turn_handler import (
                    generate_thread_response,
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
                    await generate_thread_response(
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
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                new_callable=AsyncMock,
            ),
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                return_value={"configurable": {}},
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                return_value={},
            ),
            patch(
                "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import generate_thread_response

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

            reply = await generate_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert "重复工具调用" in reply.content
            assert reply.metadata.get("guard") == "graph_recursion_fallback"


class TestThreadTurnHandlerCancellation:
    """Cancellation should still settle thread status and refunds."""

    @pytest.mark.asyncio
    async def test_complete_turn_marks_thread_failed_when_cancelled(self):
        handler = ThreadTurnHandler(thread_service=MagicMock())
        request = MagicMock()
        request.message = "hello"
        thread = MagicMock()
        prepared = PreparedThreadTurn(request=request, thread=thread)

        handler._generate_thread_response = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        handler._refund_thread_turn_billing = AsyncMock()
        handler._fail_thread_turn = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await handler.complete_turn(prepared, actor_id="user-1")

        handler._refund_thread_turn_billing.assert_not_awaited()
        handler._fail_thread_turn.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_persist_thread_reply_enqueues_incremental_memory_messages(self):
        thread_service = MagicMock()
        assistant_message = {
            "role": "assistant",
            "content": "已启动任务",
            "blocks": [
                {
                    "type": "warning",
                    "data": {"detail": "请先补充参数。"},
                }
            ],
            "metadata": {
                "orchestration": {
                    "feature_id": "deep_research",
                    "status": "awaiting_user_input",
                }
            },
        }
        thread_service.add_message = AsyncMock(return_value=assistant_message)
        thread_service.set_title_if_empty = AsyncMock()

        handler = ThreadTurnHandler(thread_service=thread_service)
        thread = SimpleNamespace(id="thread-1", workspace_id="ws-1", skill=None)
        reply = SimpleNamespace(
            content=assistant_message["content"],
            blocks=assistant_message["blocks"],
            metadata=assistant_message["metadata"],
        )

        capture_service = MagicMock()
        capture_service.capture_messages = AsyncMock()

        with (
            patch(
                "src.application.handlers.thread_turn_handler.get_memory_capture_service",
                return_value=capture_service,
            ),
            patch("src.application.handlers.thread_turn_handler.publish_thread_updated", new=AsyncMock()),
            patch("src.application.handlers.thread_turn_handler.set_thread_status", new=AsyncMock()),
        ):
            await handler._persist_thread_reply(
                thread=thread,
                actor_id="user-1",
                user_message="继续推进这个任务",
                reply=reply,
            )

        capture_service.capture_messages.assert_awaited_once()
        messages = capture_service.capture_messages.await_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "继续推进这个任务"
        assert messages[1]["role"] == "assistant"
        assert "orchestration" in messages[1]["content"]
        assert "warning" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_get_or_create_owned_thread_rejects_workspace_mismatch(self):
        thread_service = MagicMock()
        thread_service.get_or_create_thread = AsyncMock(
            return_value=SimpleNamespace(
                id="thread-1",
                workspace_id="ws-thread",
            )
        )
        handler = ThreadTurnHandler(thread_service=thread_service)

        request = SimpleNamespace(
            thread_id="thread-1",
            workspace_id="ws-request",
            model=None,
            skill=None,
            skill_explicit=False,
        )

        with pytest.raises(BadRequestError, match="requested workspace"):
            await handler._get_or_create_owned_thread(request, actor_id="user-1")

    @pytest.mark.asyncio
    async def test_prepare_turn_checks_chat_budget_before_persisting_user_message(self):
        thread = SimpleNamespace(
            id="thread-1",
            workspace_id="ws-1",
            workspace_type="sci",
            skill=None,
            messages=[],
        )
        thread_service = MagicMock()
        thread_service.get_or_create_thread = AsyncMock(return_value=thread)
        thread_service.add_message = AsyncMock()
        handler = ThreadTurnHandler(thread_service=thread_service)
        request = ThreadTurnRequest(message="解释一下研究空白", workspace_id="ws-1")

        with patch(
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            new=AsyncMock(side_effect=PaymentRequiredError("no credits")),
        ):
            with pytest.raises(PaymentRequiredError):
                await handler.prepare_turn(request, actor_id="user-1")

        thread_service.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_run_interruption_rolls_back_user_message(self):
        thread_service = MagicMock()
        thread_service.list_thread_messages = AsyncMock(
            return_value=[{"role": "user", "content": "继续"}]
        )
        thread_service.rollback_last_user_message = AsyncMock(return_value=True)
        handler = ThreadTurnHandler(thread_service=thread_service)

        prepared = PreparedThreadTurn(
            request=SimpleNamespace(message="继续"),
            thread=SimpleNamespace(
                id="thread-1",
                workspace_id="ws-1",
                skill="framework_outline",
            ),
        )

        with (
            patch("src.application.handlers.thread_turn_handler.publish_thread_updated", new=AsyncMock()) as publish_thread_updated,
        ):
            await handler.handle_run_interruption(prepared, rollback=True)

        thread_service.rollback_last_user_message.assert_awaited_once_with(
            prepared.thread,
            expected_content="继续",
            source_messages=[{"role": "user", "content": "继续"}],
        )
        publish_thread_updated.assert_awaited_once_with(prepared.thread)

    @pytest.mark.asyncio
    async def test_stream_thread_response_yields_incremental_chunks_and_final_reply(self):
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
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=_FakeStreamingAgent(),
            ),
            patch(
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                new_callable=AsyncMock,
            ),
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                return_value={"configurable": {}},
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                return_value={},
            ),
            patch(
                "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.get_model_config",
                return_value=SimpleNamespace(model="test-model", supports_streaming=True),
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import stream_thread_response

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

            stream = stream_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )
            chunks = [chunk async for chunk in stream]
            reply = await stream.wait_reply()

            assert chunks == [
                ThreadStreamDelta(kind="reasoning", text="think"),
                ThreadStreamDelta(kind="content", text="hello "),
                ThreadStreamDelta(kind="content", text="world"),
            ]
            assert reply.content == "hello world"
            assert reply.blocks[0]["type"] == "reasoning"
            assert reply.blocks[0]["data"]["text"] == "reasoning summary"

    @pytest.mark.asyncio
    async def test_stream_thread_response_surfaces_launch_feature_tool_result(self):
        tool_result = {
            "status": "launched",
            "execution_id": "exec-1",
            "feature_id": "sci_literature_positioning",
            "message": "已启动",
        }
        stream_result = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "launch_feature",
                            "args": {
                                "feature_id": "sci_literature_positioning",
                                "params": {"topic": "test"},
                            },
                            "id": "call-1",
                        }
                    ],
                ),
                ToolMessage(content=json.dumps(tool_result), tool_call_id="call-1"),
                AIMessage(content="已启动。"),
            ],
            "response_blocks": [],
            "response_metadata": {},
        }

        class _FakeAgentStreamRun:
            async def _iterate(self):
                yield (
                    "messages",
                    (
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "launch_feature",
                                    "args": {
                                        "feature_id": "sci_literature_positioning",
                                        "params": {"topic": "test"},
                                    },
                                    "id": "call-1",
                                }
                            ],
                        ),
                        {"langgraph_node": "agent"},
                    ),
                )
                yield (
                    "messages",
                    (
                        ToolMessage(content=json.dumps(tool_result), tool_call_id="call-1"),
                        {"langgraph_node": "tools"},
                    ),
                )
                yield (
                    "messages",
                    (
                        AIMessage(content="已启动。"),
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
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=_FakeStreamingAgent(),
            ),
            patch(
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                new_callable=AsyncMock,
            ),
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                return_value={"configurable": {}},
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                return_value={},
            ),
            patch(
                "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.get_model_config",
                return_value=SimpleNamespace(model="test-model", supports_streaming=True),
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import stream_thread_response

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

            stream = stream_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )
            chunks = [chunk async for chunk in stream]
            reply = await stream.wait_reply()

            assert chunks == [
                ThreadStreamDelta(
                    kind="tool_invocation",
                    data={
                        "tool": "launch_feature",
                        "args": {
                            "feature_id": "sci_literature_positioning",
                            "params": {"topic": "test"},
                        },
                    },
                ),
                ThreadStreamDelta(kind="tool_result", data=tool_result),
                ThreadStreamDelta(kind="content", text="已启动。"),
            ]
            assert reply.blocks[0]["kind"] == "tool_invocation"
            assert reply.blocks[1]["kind"] == "tool_result"
            assert reply.blocks[1]["data"]["execution_id"] == "exec-1"

    def test_reply_from_agent_result_blocks_unbacked_launch_receipt(self):
        reply = _reply_from_agent_result(
            {
                "messages": [
                    AIMessage(
                        content=(
                            "✅ 「可复现性检查」已启动，执行 ID："
                            "f89cd34a-a5e9-46eb-8189-3e6597c7335c"
                        )
                    )
                ],
                "response_blocks": [],
                "response_metadata": {},
            },
            thread_id="thread-1",
        )

        assert reply.metadata["guard"] == "unbacked_launch_receipt"
        assert "没有成功启动" in reply.content
        assert reply.blocks[0]["type"] == "warning"
        assert "f89cd34a" not in reply.content

    @pytest.mark.asyncio
    async def test_generate_thread_response_extracts_reasoning_into_blocks(self):
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
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=fake_agent,
            ),
            patch(
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                new_callable=AsyncMock,
            ),
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="deepseek-v4-pro",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                return_value={"configurable": {}},
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                return_value={},
            ),
            patch(
                "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import generate_thread_response

            mock_request = MagicMock()
            mock_request.model = "deepseek-v4-pro"
            mock_request.message = "hello"
            mock_request.attachments = ()
            mock_request.metadata = None

            mock_thread = MagicMock()
            mock_thread.id = "thread-1"
            mock_thread.skill = None
            mock_thread.model = None
            mock_thread.workspace_id = "ws-1"
            mock_thread.messages = []

            reply = await generate_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert reply.content == "final answer"
            assert reply.blocks[0]["type"] == "reasoning"
            assert "step 1" in reply.blocks[0]["data"]["text"]

    @pytest.mark.asyncio
    async def test_generate_thread_response_uses_conversation_projection_messages(self):
        """Runtime context should come from DataService projection messages."""
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={"messages": [SimpleNamespace(content="projected answer")]}
        )

        with (
            patch(
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=fake_agent,
            ),
            patch(
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import generate_thread_response

            mock_request = MagicMock()
            mock_request.model = "test-model"
            mock_request.message = "hello"
            mock_request.attachments = ()
            mock_request.metadata = None
            mock_request.thinking_enabled = False
            mock_request.reasoning_effort = None

            mock_thread = SimpleNamespace(
                id="thread-1",
                skill=None,
                model=None,
                workspace_id="ws-1",
                messages=[{"role": "user", "content": "raw bridge"}],
            )

            await generate_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
                conversation_messages=[{"role": "user", "content": "canonical projection"}],
                budget_checked=True,
            )

        initial_state = fake_agent.ainvoke.await_args.args[0]
        assert initial_state["messages"][0].content == "canonical projection"

    @pytest.mark.asyncio
    async def test_generate_thread_response_skips_pre_bridge_for_freeform_chat(self):
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
                "src.agents.chat_agent.agent.build_pipeline",
                return_value=[],
            ),
            patch(
                "src.agents.chat_agent.agent.make_chat_agent",
                return_value=fake_agent,
            ),
            patch(
                "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                new_callable=AsyncMock,
                return_value=None,
            ) as ensure_budget,
            patch(
                "src.application.handlers.thread_turn_handler.route_chat_model",
                return_value="test-model",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                return_value={"configurable": {}},
            ),
            patch(
                "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                return_value={},
            ),
            patch(
                "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                return_value="ws-1",
            ),
            patch(
                "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                return_value=None,
            ),
        ):
            from src.application.handlers.thread_turn_handler import generate_thread_response

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

            reply = await generate_thread_response(
                mock_request,
                mock_thread,
                actor_id="user-1",
            )

            assert reply.content == "agent answer"
            fake_agent.ainvoke.assert_awaited_once()
            ensure_budget.assert_awaited_once()

    async def test_stream_thread_response_timeout_surfaces_application_error(self):
        original = LLMSettings.AGENT_TIMEOUT
        LLMSettings.AGENT_TIMEOUT = 0.1

        class _SlowStreamingRun:
            async def _iterate(self):
                await asyncio.sleep(10)
                if False:
                    yield None

            def __aiter__(self):
                return self._iterate()

            async def result(self):
                await asyncio.sleep(10)
                return {}

        class _SlowStreamingAgent:
            def astream_with_result(self, *args, **kwargs):
                return _SlowStreamingRun()

        try:
            with (
                patch(
                    "src.agents.chat_agent.agent.make_chat_agent",
                    return_value=_SlowStreamingAgent(),
                ),
                patch(
                    "src.agents.chat_agent.agent.build_pipeline",
                    return_value=[],
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.route_chat_model",
                    return_value="test-model",
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                    return_value={"configurable": {}},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                    return_value={},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                    return_value="ws-1",
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                    return_value=None,
                ),
            ):
                from src.application.handlers.thread_turn_handler import stream_thread_response

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

                stream = stream_thread_response(
                    mock_request,
                    mock_thread,
                    actor_id="user-1",
                )
                with pytest.raises(ApplicationError, match="超时"):
                    async for _ in stream:
                        pass
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
                    "src.agents.chat_agent.agent.make_chat_agent",
                    return_value=mock_agent,
                ),
                patch(
                    "src.agents.chat_agent.agent.build_pipeline",
                    return_value=[],
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.route_chat_model",
                    return_value="test-model",
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
                    return_value={"configurable": {}},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.build_thread_initial_state",
                    return_value={},
                ),
                patch(
                    "src.application.handlers.thread_turn_handler._resolve_workspace_id",
                    return_value=None,
                ),
                patch(
                    "src.application.handlers.thread_turn_handler.extract_usage_from_agent_result",
                    return_value=None,
                ),
            ):
                from src.application.handlers.thread_turn_handler import (
                    generate_thread_response,
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

                reply = await generate_thread_response(
                    mock_request,
                    mock_thread,
                    actor_id="user-1",
                )
                # Should return a GeneratedThreadReply without raising
                assert reply is not None
        finally:
            LLMSettings.AGENT_TIMEOUT = original
