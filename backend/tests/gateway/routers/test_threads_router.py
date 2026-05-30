"""Tests for thread management router and turn-runtime helpers."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.application.handlers.thread_turn_handler import (
    _build_langchain_messages,
    build_thread_initial_state,
    build_thread_runtime_config,
    generate_thread_response,
)
from src.application.results import (
    ThreadTurnRequest,
)
from src.gateway.routers import threads
from src.gateway.routers.auth import get_current_user
from src.models.router import InvalidRequestedModelError
from src.services.thread_service import ThreadAccessError


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
    workspace: object | None = None
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeThreadService:
    """In-memory thread service used to exercise router behavior."""

    def __init__(self) -> None:
        self.threads: dict[str, FakeThread] = {}
        self.canonical_messages: dict[str, list[dict]] = {}
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
            workspace=SimpleNamespace(type="thesis") if workspace_id else None,
        )
        self.threads[thread.id] = thread
        return thread

    @staticmethod
    def resolve_requested_model(model: str | None) -> str | None:
        if model is None:
            return None
        if model.strip() == "bad-model":
            raise InvalidRequestedModelError("Unknown model id: bad-model")
        return model.strip() or None

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
                    raise ThreadAccessError("Thread not found")
                if workspace_id and not thread.workspace_id:
                    thread.workspace_id = workspace_id
                    thread.workspace = SimpleNamespace(type="thesis")
                    thread.updated_at = datetime.now(UTC)
                if skill_explicit:
                    thread.skill = skill
                return thread
            raise ThreadAccessError("Thread not found")

        if workspace_id:
            workspace_threads = [
                thread
                for thread in self.threads.values()
                if thread.user_id == user_id and thread.workspace_id == workspace_id
            ]
            workspace_threads.sort(
                key=lambda thread: thread.updated_at,
                reverse=True,
            )
            if workspace_threads:
                thread = workspace_threads[0]
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
        self.canonical_messages[thread.id] = [*self.canonical_messages.get(thread.id, thread.messages[:-1]), message]
        thread.updated_at = resolved_timestamp
        return message

    async def set_title_if_empty(self, thread: FakeThread, first_message: str) -> None:
        if thread.title or len(thread.messages) > 2:
            return
        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(UTC)

    async def list_thread_messages(self, thread: FakeThread) -> list[dict]:
        return list(self.canonical_messages.get(thread.id, thread.messages))

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


def create_client(user_id: str, service: FakeThreadService) -> TestClient:
    """Create a test client with overridden auth and thread service."""
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_thread_service():
        return service

    async def allow_workspace_owner(*args, **kwargs):
        workspace_id = kwargs.get("workspace_id")
        return SimpleNamespace(id=workspace_id)

    threads.require_workspace_owner_by_dataservice = allow_workspace_owner
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[threads.get_thread_service] = (
        override_get_thread_service
    )
    app.include_router(threads.router)
    return TestClient(app)


class TestThreadManagementRoutes:
    """Thread ownership and lifecycle tests."""

    def test_create_and_get_thread(self):
        """Users can create and retrieve their own threads."""
        service = FakeThreadService()
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

    def test_get_thread_detail_reads_canonical_conversation_projection(self):
        """Thread detail reads message payloads through the DataService projection boundary."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        response = client.post(
            "/threads",
            json={"workspace_id": "ws-1", "title": "Thread 1"},
        )
        thread_id = response.json()["id"]
        service.threads[thread_id].messages = [{"role": "user", "content": "bridge"}]
        service.canonical_messages[thread_id] = [
            {
                "role": "assistant",
                "content": "canonical",
                "blocks": [{"kind": "text", "content": "canonical"}],
            }
        ]

        response = client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["messages"][0]["role"] == "assistant"
        assert payload["messages"][0]["content"] == "canonical"
        assert payload["messages"][0]["blocks"] == [{"kind": "text", "content": "canonical"}]

    def test_create_thread_rejects_invalid_model_selection(self):
        """Explicit invalid model ids should fail instead of silently rerouting."""
        service = FakeThreadService()
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

    def test_create_thread_rejects_unowned_workspace(self):
        """Workspace-bound thread creation should enforce workspace ownership."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.gateway.routers.threads.require_workspace_owner_by_dataservice",
            AsyncMock(side_effect=HTTPException(status_code=403, detail="Access denied")),
        ):
            response = client.post(
                "/threads",
                json={"workspace_id": "ws-foreign", "title": "Thread 1"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_ensure_workspace_thread_reuses_workspace_main_thread(self):
        """Workspace thread endpoint should return the canonical workspace thread."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        first = client.post(
            "/workspaces/ws-1/thread",
            json={"skill": "deep-research"},
        )
        second = client.post(
            "/workspaces/ws-1/thread",
            json={},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["workspace_id"] == "ws-1"


class TestThreadManagementContinuation:
    """Additional thread ownership and lifecycle tests."""

    def test_thread_access_is_isolated_by_user(self):
        """A thread owned by one user is hidden from another."""
        service = FakeThreadService()
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
        service = FakeThreadService()
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
        service = FakeThreadService()
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
        service = FakeThreadService()
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

    def test_list_threads_rejects_invalid_limit_bounds(self):
        """Thread list limit should be bounded to protect backend resources."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        too_small = client.get("/threads?limit=0")
        too_large = client.get("/threads?limit=101")

        assert too_small.status_code == 422
        assert too_large.status_code == 422

    def test_list_threads_rejects_unowned_workspace_filter(self):
        """Workspace-scoped history listing should enforce workspace ownership."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.gateway.routers.threads.require_workspace_owner_by_dataservice",
            AsyncMock(side_effect=HTTPException(status_code=403, detail="Access denied")),
        ):
            response = client.get("/threads?workspace_id=ws-foreign")

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"


class TestChatRuntimeConfig:
    """Runtime config assembly for chat-agent invocations."""

    def test_runtime_config_disables_subagent_without_execution_session(self):
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.model_supports_vision",
            return_value=True,
        ):
            config = build_thread_runtime_config(
                request=request,
                thread=thread,
                actor_id="user-1",
                workspace_id="ws-1",
                effective_skill=None,
                effective_model="gpt-4o",
            )

        assert config["configurable"]["supports_vision"] is True
        assert "subagent_enabled" not in config["configurable"]
        assert "max_concurrent_subagents" not in config["configurable"]

    def test_runtime_config_enables_subagent_with_execution(self):
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.model_supports_vision",
            return_value=True,
        ):
            config = build_thread_runtime_config(
                request=request,
                thread=thread,
                actor_id="user-1",
                workspace_id="ws-1",
                effective_skill=None,
                effective_model="gpt-4o",
                execution_id="exec-1",
            )

        assert "subagent_enabled" not in config["configurable"]
        assert config["configurable"]["execution_id"] == "exec-1"

    def test_initial_state_includes_uploaded_files_and_viewed_images(self, tmp_path):
        from src.application.results import ThreadTurnAttachment

        attachment = ThreadTurnAttachment(
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
            "src.application.handlers.thread_turn_handler.get_thread_data_root",
            return_value=thread_root,
        ):
            state = build_thread_initial_state(
                thread,
                actor_id="user-1",
                workspace_id="ws-1",
                effective_skill=None,
                attachments=(attachment,),
            )

        assert state["uploaded_files"][0]["name"] == "figure.png"
        assert "/mnt/user-data/uploads/figure.png" in state["viewed_images"]

    def test_build_langchain_messages_preserves_structured_message_context(self):
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": "请帮我开始「框架与摘要」。",
                    "metadata": {
                        "orchestration": {
                            "feature_id": "framework_outline",
                            "params": {"topic": "LLM planning"},
                        }
                    },
                },
                {
                    "role": "assistant",
                    "content": "已启动任务",
                    "blocks": [
                        {
                            "type": "task",
                            "title": "论文写作",
                            "data": {"task_id": "task-1", "status": "pending"},
                        }
                    ],
                    "metadata": {
                        "orchestration": {
                            "feature_id": "writing",
                            "task_id": "task-1",
                            "status": "running",
                        }
                    },
                },
            ],
        )

        messages = _build_langchain_messages(thread.messages)

        assert len(messages) == 2
        user_content = messages[0].content
        assert isinstance(user_content, str)
        assert user_content == "请帮我开始「框架与摘要」。"
        assistant_content = messages[-1].content
        assert isinstance(assistant_content, str)
        assert "已启动任务" in assistant_content
        assert "feature=writing" in assistant_content
        assert "task_id=task-1" in assistant_content

    def test_build_langchain_messages_preserves_plain_user_content(self):
        thread = FakeThread(
            id="thread-2",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 2",
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": "请帮我开始「框架与摘要」。",
                    "metadata": {
                        "orchestration": {
                            "feature_id": "framework_outline",
                            "params": {"topic": "LLM planning"},
                        }
                    },
                },
                {"role": "assistant", "content": "好的，我们先从结构开始。"},
                {"role": "user", "content": "这个方法为什么有效？"},
            ],
        )

        messages = _build_langchain_messages(thread.messages)

        assert messages[0].content == "请帮我开始「框架与摘要」。"
        assert messages[-1].content == "这个方法为什么有效？"

    def test_build_langchain_messages_surfaces_continue_thread_action_context(self):
        thread = FakeThread(
            id="thread-3",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 3",
            model="gpt-4o",
            messages=[
                {
                    "role": "assistant",
                    "content": "这是上一轮结果。",
                    "metadata": {
                        "orchestration": {
                            "feature_id": "writing",
                            "execution_id": "exec-9",
                        }
                    },
                },
                {
                    "role": "user",
                    "content": "retry_run",
                    "metadata": {
                        "orchestration": {
                            "feature_id": "writing",
                            "execution_id": "exec-9",
                        },
                        "block_action": {
                            "action": "continue_thread",
                            "intent": "retry_run",
                            "source_block_kind": "result_card",
                        },
                    },
                },
            ],
        )

        messages = _build_langchain_messages(thread.messages)

        user_content = messages[-1].content
        assert isinstance(user_content, str)
        assert "retry_run" in user_content
        assert "feature=writing" in user_content
        assert "execution_id=exec-9" in user_content
        assert "action=continue_thread" in user_content
        assert "intent=retry_run" in user_content
        assert "source=result_card" in user_content

    def test_build_langchain_messages_restores_assistant_reasoning_content(self):
        thread = FakeThread(
            id="thread-4",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 4",
            model="gpt-4o",
            messages=[
                {
                    "role": "assistant",
                    "content": "你好！我是 Wenjin 研究助手。",
                    "metadata": {
                        "reasoning": {
                            "text": "用户打了招呼，所以我先问研究方向。"
                        }
                    },
                }
            ],
        )

        messages = _build_langchain_messages(thread.messages)

        assert len(messages) == 1
        assistant_message = messages[0]
        assert assistant_message.content == "你好！我是 Wenjin 研究助手。"
        assert assistant_message.additional_kwargs["reasoning"] == "用户打了招呼，所以我先问研究方向。"
        assert assistant_message.additional_kwargs["reasoning_content"] == "用户打了招呼，所以我先问研究方向。"


class TestThreadMessages:
    """Chat message flow tests."""

    def test_chat_endpoint_removed_in_favor_of_runs_api(self):
        """Legacy /chat must stay removed after direct run architecture migration."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        response = client.post(
            "/chat",
            json={"message": "Hello", "workspace_id": "ws-1"},
        )

        assert response.status_code == 404

    def test_chat_stream_endpoint_removed_in_favor_of_runs_api(self):
        """Legacy /chat/stream must stay removed after direct run architecture migration."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        response = client.post(
            "/chat/stream",
            json={"message": "Hello stream", "workspace_id": "ws-stream"},
        )

        assert response.status_code == 404

    def test_thread_agent_status_endpoint_removed_in_favor_of_threads_state(self):
        """Legacy /threads/{id}/agent-status must stay removed after runs migration."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        created = client.post(
            "/threads",
            json={"workspace_id": "ws-1", "skill": "deep-research"},
        )
        thread_id = created.json()["id"]

        response = client.get(f"/threads/{thread_id}/agent-status")

        assert response.status_code == 404

    def test_workspace_chat_thread_endpoint_removed_in_favor_of_workspace_thread(self):
        """Legacy /workspaces/{id}/chat-thread must stay removed."""
        service = FakeThreadService()
        client = create_client("user-1", service)

        response = client.post(
            "/workspaces/ws-1/chat-thread",
            json={},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_thread_response_preserves_structured_tool_state(self):
        """Structured tool updates should survive the agent chat path."""
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.chat_agent.agent.build_pipeline",
            return_value=[],
        ), patch(
            "src.agents.chat_agent.agent.make_chat_agent",
            return_value=fake_agent,
        ):
            reply = await generate_thread_response(
                request,
                thread,
                actor_id="user-1",
                execution_id="exec-1",
            )

        assert reply.content == "模块已启动"
        assert reply.blocks[0]["type"] == "task"
        assert reply.metadata["orchestration"]["task_id"] == "task-1"
        assert reply.metadata["orchestration"]["execution_id"] == "exec-1"
        assert reply.metadata["usage"]["total_tokens"] == 150
        assert reply.metadata["usage"]["source"] == "thread_agent"

    @pytest.mark.asyncio
    async def test_generate_thread_response_carries_forward_safe_orchestration_seed(self):
        """Assistant replies should retain canonical launch context for follow-up turns."""
        request = ThreadTurnRequest(
            message="继续这轮写作",
            workspace_id="ws-1",
            attachments=(),
            metadata={
                "orchestration": {
                    "intent": "launch",
                    "feature_id": "writing",
                    "params": {
                        "source_artifact_id": "artifact-1",
                        "context_artifact_ids": ["artifact-1", "artifact-2"],
                    },
                }
            },
        )
        thread = FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="Thread 1",
            model="gpt-4o",
            skill="section-writer",
        )
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [MagicMock(content="好的，我继续写。")],
                "response_metadata": {
                    "orchestration": {"task_id": "task-2"}
                },
            }
        )

        with patch(
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.chat_agent.agent.build_pipeline",
            return_value=[],
        ), patch(
            "src.agents.chat_agent.agent.make_chat_agent",
            return_value=fake_agent,
        ):
            reply = await generate_thread_response(
                request,
                thread,
                actor_id="user-1",
                execution_id="exec-2",
            )

        assert reply.metadata["orchestration"] == {
            "task_id": "task-2",
            "feature_id": "writing",
            "params": {
                "source_artifact_id": "artifact-1",
                "context_artifact_ids": ["artifact-1", "artifact-2"],
            },
            "execution_id": "exec-2",
        }

    @pytest.mark.asyncio
    async def test_generate_thread_response_builds_artifact_block_from_agent_state(self):
        """Agent-presented files should become structured chat artifacts."""
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.chat_agent.agent.build_pipeline",
            return_value=[],
        ), patch(
            "src.agents.chat_agent.agent.make_chat_agent",
            return_value=fake_agent,
        ):
            reply = await generate_thread_response(request, thread, actor_id="user-1")

        assert reply.blocks[0]["type"] == "artifacts"
        assert reply.metadata["artifacts"][0]["url"].endswith(
            "/api/threads/thread-1/artifacts/mnt/user-data/outputs/report.md"
        )
        assert reply.content == "已生成 1 个文件，可直接打开查看。"

    @pytest.mark.asyncio
    async def test_generate_thread_response_propagates_budget_http_errors(self):
        """Budget failures must not be swallowed by the agent fallback path."""
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(side_effect=HTTPException(status_code=402, detail="余额不足")),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.chat_agent.agent.build_pipeline",
            return_value=[],
        ):
            with pytest.raises(HTTPException, match="余额不足") as exc_info:
                await generate_thread_response(request, thread, actor_id="user-1")

        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_generate_thread_response_disables_middleware_memory_capture(self):
        """Chat router should rely on persisted-turn capture, not middleware double capture."""
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="gpt-4o",
        ), patch(
            "src.agents.chat_agent.agent.build_pipeline",
            build_pipeline,
        ), patch(
            "src.agents.chat_agent.agent.make_chat_agent",
            return_value=fake_agent,
        ):
            await generate_thread_response(request, thread, actor_id="user-1")

        assert build_pipeline.call_args.kwargs["memory_capture_enabled"] is False

    @pytest.mark.asyncio
    async def test_generate_thread_response_propagates_agent_failures_without_fallback(self):
        """Lead-agent failures should surface instead of silently switching execution paths."""
        request = ThreadTurnRequest(
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
            "src.application.handlers.thread_turn_handler.ensure_thread_turn_budget",
            AsyncMock(return_value=None),
        ), patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="glm-5",
        ), patch(
            "src.agents.chat_agent.agent.make_chat_agent",
            side_effect=RuntimeError("boom"),
        ), patch(
            "src.models.factory.create_chat_model",
        ) as create_chat_model:
            with pytest.raises(RuntimeError, match="boom"):
                await generate_thread_response(request, thread, actor_id="user-1")

        create_chat_model.assert_not_called()
