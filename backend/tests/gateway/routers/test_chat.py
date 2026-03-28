"""Tests for chat router."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.application.errors import PaymentRequiredError
from src.application.handlers.chat_turn_handler import (
    ChatTurnHandler,
    build_chat_initial_state,
    build_chat_runtime_config,
    generate_chat_response,
)
from src.application.results import (
    ChatTurnRequest,
    GeneratedChatReply,
)
from src.gateway.routers import chat
from src.gateway.routers.auth import get_current_user
from src.models.router import InvalidRequestedModelError
from src.services.chat_thread_service import ChatThreadAccessError


def create_mock_user(user_id: str) -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = user_id
    return user


@dataclass
class FakeThread:
    """Minimal thread object used by router tests."""

    id: str
    user_id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None = None
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeChatThreadService:
    """In-memory thread service used to exercise router behavior."""

    def __init__(self) -> None:
        self.threads: dict[str, FakeThread] = {}
        self._counter = 0

    def _new_thread_id(self) -> str:
        self._counter += 1
        return f"thread-{self._counter}"

    async def create_thread(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        model: str | None = None,
        skill: str | None = None,
    ) -> FakeThread:
        thread = FakeThread(
            id=self._new_thread_id(),
            user_id=user_id,
            workspace_id=workspace_id,
            title=title,
            model=model or "default",
            skill=skill,
        )
        self.threads[thread.id] = thread
        return thread

    async def get_thread(self, thread_id: str, user_id: str) -> FakeThread | None:
        thread = self.threads.get(thread_id)
        if not thread or thread.user_id != user_id:
            return None
        return thread

    async def get_or_create_thread(
        self,
        *,
        user_id: str,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
        skill: str | None = None,
        skill_explicit: bool = False,
    ) -> FakeThread:
        if thread_id:
            thread = self.threads.get(thread_id)
            if thread:
                if thread.user_id != user_id:
                    raise ChatThreadAccessError("Thread not found")
                if workspace_id and not thread.workspace_id:
                    thread.workspace_id = workspace_id
                    thread.updated_at = datetime.now(UTC)
                if skill_explicit:
                    thread.skill = skill
                return thread

        return await self.create_thread(
            user_id=user_id,
            workspace_id=workspace_id,
            model=model,
            skill=skill if skill_explicit else None,
        )

    async def add_message(
        self,
        thread: FakeThread,
        *,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        blocks: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> dict[str, object]:
        resolved_timestamp = timestamp or datetime.now(UTC)
        message = {
            "role": role,
            "content": content,
            "timestamp": resolved_timestamp.isoformat(),
        }
        if blocks:
            message["blocks"] = blocks
        if metadata:
            message["metadata"] = metadata
        thread.messages = [*thread.messages, message]
        thread.updated_at = resolved_timestamp
        return message

    async def set_title_if_empty(self, thread: FakeThread, first_message: str) -> None:
        if thread.title or len(thread.messages) > 2:
            return
        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(UTC)

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[FakeThread]:
        threads = [
            thread
            for thread in self.threads.values()
            if thread.user_id == user_id
        ]
        if workspace_id:
            threads = [thread for thread in threads if thread.workspace_id == workspace_id]
        threads.sort(key=lambda thread: thread.updated_at, reverse=True)
        return threads[:limit]

    async def delete_thread(self, thread_id: str, user_id: str) -> bool:
        thread = await self.get_thread(thread_id, user_id)
        if not thread:
            return False
        del self.threads[thread_id]
        return True


class _FakeDbContext:
    """Tiny async context manager used to stub get_db_session."""

    def __init__(self, db: object) -> None:
        self._db = db

    async def __aenter__(self) -> object:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeBillingResult:
    """Billing result shim matching ChatCreditConsumption.as_metadata()."""

    def __init__(self, metadata: dict[str, object]) -> None:
        self._metadata = metadata

    def as_metadata(self) -> dict[str, object]:
        return dict(self._metadata)


def create_client(user_id: str, service: FakeChatThreadService) -> TestClient:
    """Create a test client with overridden auth and chat thread service."""
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_chat_thread_service():
        return service

    async def override_get_chat_turn_handler():
        return ChatTurnHandler(chat_thread_service=service)

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[chat.get_chat_thread_service] = (
        override_get_chat_thread_service
    )
    app.dependency_overrides[chat.get_chat_turn_handler] = (
        override_get_chat_turn_handler
    )
    app.include_router(chat.router)
    return TestClient(app)


class TestChatThreads:
    """Thread ownership and lifecycle tests."""

    def test_create_and_get_thread(self):
        """Users can create and retrieve their own threads."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        response = client.post(
            "/threads",
            json={"workspace_id": "ws-1", "title": "Thread 1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "ws-1"
        assert data["title"] == "Thread 1"
        assert data["skill"] is None

        thread_id = data["id"]
        response = client.get(f"/threads/{thread_id}")
        assert response.status_code == 200
        assert response.json()["id"] == thread_id

    def test_create_thread_rejects_invalid_model_selection(self):
        """Explicit invalid model ids should fail instead of silently rerouting."""
        service = FakeChatThreadService()
        service.create_thread = AsyncMock(
            side_effect=InvalidRequestedModelError("Unknown model id: bad-model")
        )
        client = create_client("user-1", service)

        response = client.post(
            "/threads",
            json={"workspace_id": "ws-1", "model": "bad-model"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Unknown model id: bad-model"


class TestChatThreadsContinuation:
    """Additional thread ownership and lifecycle tests."""

    def test_thread_access_is_isolated_by_user(self):
        """A thread owned by one user is hidden from another."""
        service = FakeChatThreadService()
        owner_client = create_client("user-1", service)
        other_client = create_client("user-2", service)

        response = owner_client.post("/threads", json={})
        thread_id = response.json()["id"]

        response = other_client.get(f"/threads/{thread_id}")
        assert response.status_code == 404

        response = other_client.delete(f"/threads/{thread_id}")
        assert response.status_code == 404

    def test_list_threads_filters_by_current_user(self):
        """Thread listing only returns the current user's threads."""
        service = FakeChatThreadService()
        owner_client = create_client("user-1", service)
        other_client = create_client("user-2", service)

        owner_client.post("/threads", json={"title": "Owner thread"})
        other_client.post("/threads", json={"title": "Other thread"})

        response = owner_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["threads"][0]["title"] == "Owner thread"

    def test_list_threads_includes_persisted_skill(self):
        """Thread summaries expose the persisted session skill."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        client.post(
            "/threads",
            json={"title": "Skill thread", "skill": "deep-research"},
        )

        response = client.get("/threads")

        assert response.status_code == 200
        assert response.json()["threads"][0]["skill"] == "deep-research"

    def test_list_threads_includes_last_message_preview(self):
        """Thread summaries expose a compact preview for history UI."""
        service = FakeChatThreadService()
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title=None,
            model="default",
            messages=[
                {"role": "user", "content": "first prompt"},
                {
                    "role": "assistant",
                    "content": "This is a fairly long assistant reply for preview rendering.",
                },
            ],
        )
        service.threads[thread.id] = thread
        client = create_client("user-1", service)

        response = client.get("/threads")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["threads"][0]["message_count"] == 2
        assert payload["threads"][0]["last_message_role"] == "assistant"
        assert payload["threads"][0]["last_message_preview"] == (
            "This is a fairly long assistant reply for preview rendering."
        )


class TestChatRuntimeConfig:
    """Runtime config assembly for chat-agent invocations."""

    def test_runtime_config_includes_vision_and_subagent_flags(self):
        request = ChatTurnRequest(
            message="Hello",
            workspace_id="ws-1",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
        )

        with patch(
            "src.application.handlers.chat_turn_handler.get_model_config",
            return_value=MagicMock(model="gpt-4o"),
        ), patch(
            "src.application.handlers.chat_turn_handler.get_app_config",
            return_value=MagicMock(subagents=MagicMock(enabled=True, max_concurrent=4)),
        ):
            config = build_chat_runtime_config(
                request=request,
                thread=thread,
                actor_id="user-1",
                workspace_id="ws-1",
                effective_skill=None,
                effective_model="gpt-4o",
            )

        assert config["configurable"]["supports_vision"] is True
        assert config["configurable"]["subagent_enabled"] is True
        assert config["configurable"]["max_concurrent_subagents"] == 4

    def test_initial_state_includes_uploaded_files_and_viewed_images(self, tmp_path):
        from src.application.results import ChatTurnAttachment

        attachment = ChatTurnAttachment(
            name="figure.png",
            path="/mnt/user-data/uploads/figure.png",
            kind="transient",
            content_type="image/png",
            size_bytes=8,
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
        )
        thread_root = tmp_path / "threads" / "thread-1" / "user-data"
        uploads_dir = thread_root / "uploads"
        uploads_dir.mkdir(parents=True)
        (uploads_dir / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        with patch(
            "src.application.handlers.chat_turn_handler.get_thread_data_root",
            return_value=thread_root,
        ):
            state = build_chat_initial_state(
                thread,
                workspace_id="ws-1",
                effective_skill=None,
                attachments=(attachment,),
            )

        assert state["uploaded_files"][0]["name"] == "figure.png"
        assert "/mnt/user-data/uploads/figure.png" in state["viewed_images"]


class TestChatMessages:
    """Chat message flow tests."""

    def test_chat_persists_workspace_context_on_thread(self):
        """Chat requests keep workspace_id attached to the thread."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(return_value=GeneratedChatReply(content="assistant reply")),
        ):
            response = client.post(
                "/chat",
                json={
                    "message": "Hello",
                    "workspace_id": "ws-1",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "ws-1"

        thread_id = data["thread_id"]
        stored_thread = service.threads[thread_id]
        assert stored_thread.workspace_id == "ws-1"
        assert [message["role"] for message in stored_thread.messages] == [
            "user",
            "assistant",
        ]

    def test_chat_rejects_invalid_model_selection_before_generation(self):
        """Chat turn startup should reject invalid explicit model ids."""
        service = FakeChatThreadService()
        service.get_or_create_thread = AsyncMock(
            side_effect=InvalidRequestedModelError("Unknown model id: bad-model")
        )
        client = create_client("user-1", service)

        response = client.post(
            "/chat",
            json={"message": "Hello", "workspace_id": "ws-1", "model": "bad-model"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Unknown model id: bad-model"

    def test_chat_persists_selected_skill_on_thread(self):
        """Chat requests persist the selected skill on the thread."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(return_value=GeneratedChatReply(content="assistant reply")),
        ):
            response = client.post(
                "/chat",
                json={
                    "message": "Hello",
                    "workspace_id": "ws-1",
                    "skill": "deep-research",
                },
            )

        assert response.status_code == 200
        thread_id = response.json()["thread_id"]
        assert service.threads[thread_id].skill == "deep-research"
        assert response.json()["skill"] == "deep-research"

    def test_chat_can_clear_selected_skill(self):
        """Explicit null skill should clear the persisted thread skill."""
        service = FakeChatThreadService()
        service.threads["thread-1"] = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="default",
            skill="deep-research",
        )
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(return_value=GeneratedChatReply(content="assistant reply")),
        ):
            response = client.post(
                "/chat",
                json={
                    "message": "Hello",
                    "thread_id": "thread-1",
                    "skill": None,
                },
            )

        assert response.status_code == 200
        assert service.threads["thread-1"].skill is None
        assert response.json()["skill"] is None

    def test_chat_stream_returns_thread_id_and_persists_messages(self):
        """Streaming chat keeps the same persistence and SSE contract."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(return_value=GeneratedChatReply(content="stream reply")),
        ):
            response = client.post(
                "/chat/stream",
                json={"message": "Hello stream", "workspace_id": "ws-stream"},
            )

        assert response.status_code == 200
        assert '"type": "thread_id"' in response.text
        assert '"skill": null' in response.text
        assert '"type": "content"' in response.text
        assert '"type": "done"' in response.text

        assert len(service.threads) == 1
        thread = next(iter(service.threads.values()))
        assert thread.workspace_id == "ws-stream"
        assert thread.skill is None
        assert [message["role"] for message in thread.messages] == [
            "user",
            "assistant",
        ]

    def test_chat_persists_structured_assistant_message(self):
        """Structured blocks and metadata are stored on assistant messages."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(
                return_value=GeneratedChatReply(
                    content="已启动任务",
                    blocks=[{"type": "task", "title": "论文写作", "data": {"task_id": "task-1"}}],
                    metadata={"orchestration": {"task_id": "task-1", "feature_id": "writing"}},
                )
            ),
        ):
            response = client.post(
                "/chat",
                json={"message": "开始写作", "workspace_id": "ws-1"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["message"]["blocks"][0]["type"] == "task"
        assert payload["message"]["metadata"]["orchestration"]["task_id"] == "task-1"
        thread = service.threads[payload["thread_id"]]
        assert thread.messages[-1]["blocks"][0]["title"] == "论文写作"

    def test_chat_persists_usage_and_billing_metadata(self):
        """Chat replies persist token usage and settled billing summaries."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)
        fake_credit_service = MagicMock()
        fake_credit_service.consume_for_chat_usage = AsyncMock(
            return_value=_FakeBillingResult(
                {
                    "type": "chat_token_billing",
                    "token_usage": {
                        "input_tokens": 800,
                        "output_tokens": 200,
                        "total_tokens": 1000,
                    },
                    "model_name": "gpt-4o",
                    "free_tokens_applied": 1000,
                    "billable_tokens": 0,
                    "credits_charged": 0,
                    "historical_tokens_before": 0,
                    "historical_tokens_after": 1000,
                    "transaction_id": "tx-chat-1",
                    "balance_after": 100,
                    "charged": False,
                }
            )
        )

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(
                return_value=GeneratedChatReply(
                    content="assistant reply",
                    metadata={
                        "usage": {
                            "input_tokens": 800,
                            "output_tokens": 200,
                            "total_tokens": 1000,
                            "source": "chat_agent",
                            "model_name": "gpt-4o",
                        }
                    },
                )
            ),
        ), patch(
            "src.application.handlers.chat_turn_handler.get_db_session",
            return_value=_FakeDbContext(MagicMock()),
        ), patch(
            "src.application.handlers.chat_turn_handler.CreditService",
            return_value=fake_credit_service,
        ):
            response = client.post(
                "/chat",
                json={"message": "Hello", "workspace_id": "ws-1"},
            )

        assert response.status_code == 200
        payload = response.json()
        message_metadata = payload["message"]["metadata"]
        assert message_metadata["usage"]["total_tokens"] == 1000
        assert message_metadata["billing"]["transaction_id"] == "tx-chat-1"
        assert message_metadata["billing"]["credits_charged"] == 0
        thread = service.threads[payload["thread_id"]]
        assert thread.messages[-1]["metadata"]["billing"]["historical_tokens_after"] == 1000
        fake_credit_service.consume_for_chat_usage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_chat_response_preserves_structured_tool_state(self):
        """Structured tool updates should survive the agent chat path."""
        request = ChatTurnRequest(
            message="启动模块",
            workspace_id="ws-1",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
            skill="framework-designer",
        )
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    MagicMock(
                        content="模块已启动",
                        usage_metadata={"input_tokens": 120, "output_tokens": 30},
                    )
                ],
                "response_blocks": [{"type": "task", "title": "框架设计"}],
                "response_metadata": {
                    "orchestration": {"feature_id": "framework_outline", "task_id": "task-1"}
                },
            }
        )

        with patch(
            "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.lead_agent.agent.build_pipeline",
            return_value=[],
        ), patch(
            "src.agents.lead_agent.agent.make_lead_agent",
            return_value=fake_agent,
        ):
            reply = await generate_chat_response(request, thread, actor_id="user-1")

        assert reply.content == "模块已启动"
        assert reply.blocks[0]["type"] == "task"
        assert reply.metadata["orchestration"]["task_id"] == "task-1"
        assert reply.metadata["usage"]["total_tokens"] == 150
        assert reply.metadata["usage"]["source"] == "chat_agent"

    @pytest.mark.asyncio
    async def test_generate_chat_response_builds_artifact_block_from_agent_state(self):
        """Agent-presented files should become structured chat artifacts."""
        request = ChatTurnRequest(
            message="导出文件",
            workspace_id="ws-1",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
        )
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [MagicMock(content="")],
                "artifacts": ["/mnt/user-data/outputs/report.md"],
            }
        )

        with patch(
            "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.lead_agent.agent.build_pipeline",
            return_value=[],
        ), patch(
            "src.agents.lead_agent.agent.make_lead_agent",
            return_value=fake_agent,
        ):
            reply = await generate_chat_response(request, thread, actor_id="user-1")

        assert reply.blocks[0]["type"] == "artifacts"
        assert reply.metadata["artifacts"][0]["url"].endswith(
            "/api/threads/thread-1/artifacts/mnt/user-data/outputs/report.md"
        )
        assert reply.content == "已生成 1 个文件，可直接打开查看。"

    @pytest.mark.asyncio
    async def test_generate_chat_response_propagates_budget_http_errors(self):
        """Budget failures must not be swallowed by the agent fallback path."""
        request = ChatTurnRequest(
            message="继续对话",
            workspace_id="ws-1",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
        )

        with patch(
            "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
            AsyncMock(side_effect=HTTPException(status_code=402, detail="余额不足")),
        ), patch(
            "src.application.handlers.chat_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.lead_agent.agent.build_pipeline",
            return_value=[],
        ):
            with pytest.raises(HTTPException, match="余额不足") as exc_info:
                await generate_chat_response(request, thread, actor_id="user-1")

        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_generate_chat_response_disables_middleware_memory_capture(self):
        """Chat router should rely on persisted-turn capture, not middleware double capture."""
        request = ChatTurnRequest(
            message="继续对话",
            workspace_id="ws-1",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
        )
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="已收到")]}
        )
        build_pipeline = MagicMock(return_value=[])

        with patch(
            "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.lead_agent.agent.build_pipeline",
            build_pipeline,
        ), patch(
            "src.agents.lead_agent.agent.make_lead_agent",
            return_value=fake_agent,
        ):
            await generate_chat_response(request, thread, actor_id="user-1")

        assert build_pipeline.call_args.kwargs["memory_capture_enabled"] is False

    def test_thread_agent_status_defaults_to_idle(self):
        """Threads expose a default idle execution status for unified UI polling."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        create_response = client.post(
            "/threads",
            json={"workspace_id": "ws-1", "skill": "deep-research"},
        )
        thread_id = create_response.json()["id"]

        response = client.get(f"/threads/{thread_id}/agent-status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["thread_id"] == thread_id
        assert payload["status"] == "idle"
        assert payload["current_skill"] == "deep-research"

    @pytest.mark.asyncio
    async def test_generate_chat_response_propagates_agent_failures_without_fallback(self):
        """Lead-agent failures should surface instead of silently switching execution paths."""
        request = ChatTurnRequest(
            message="Hello",
            workspace_id="ws-1",
            reasoning_effort="high",
            attachments=(),
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="glm-5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        with patch(
            "src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.ensure_chat_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.chat_turn_handler.route_chat_model",
            return_value="glm-5",
        ), patch(
            "src.agents.lead_agent.agent.make_lead_agent",
            side_effect=RuntimeError("boom"),
        ), patch(
            "src.models.factory.create_chat_model",
        ) as create_chat_model:
            with pytest.raises(RuntimeError, match="boom"):
                await generate_chat_response(request, thread, actor_id="user-1")

        create_chat_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_streaming_chat_surfaces_generation_errors_as_sse_error_event(self):
        """Streaming route should still expose generation failures explicitly."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.application.handlers.chat_turn_handler.generate_chat_response",
            AsyncMock(side_effect=RuntimeError("agent boom")),
        ):
            response = client.post(
                "/chat/stream",
                json={"message": "Hello", "workspace_id": "ws-1"},
            )

        assert response.status_code == 200
        assert '"type": "error"' in response.text
        assert "agent boom" in response.text
