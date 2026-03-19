"""Tests for chat router."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import chat
from src.gateway.routers.auth import get_current_user
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
                    thread.updated_at = datetime.now(timezone.utc)
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
    ) -> dict[str, str]:
        resolved_timestamp = timestamp or datetime.now(timezone.utc)
        message = {
            "role": role,
            "content": content,
            "timestamp": resolved_timestamp.isoformat(),
        }
        thread.messages = [*thread.messages, message]
        thread.updated_at = resolved_timestamp
        return message

    async def set_title_if_empty(self, thread: FakeThread, first_message: str) -> None:
        if thread.title or len(thread.messages) > 2:
            return
        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(timezone.utc)

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


def create_client(user_id: str, service: FakeChatThreadService) -> TestClient:
    """Create a test client with overridden auth and chat thread service."""
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_chat_thread_service():
        return service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[chat.get_chat_thread_service] = (
        override_get_chat_thread_service
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


class TestChatMessages:
    """Chat message flow tests."""

    def test_chat_persists_workspace_context_on_thread(self):
        """Chat requests keep workspace_id attached to the thread."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.gateway.routers.chat._generate_chat_response",
            AsyncMock(return_value="assistant reply"),
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

    def test_chat_persists_selected_skill_on_thread(self):
        """Chat requests persist the selected skill on the thread."""
        service = FakeChatThreadService()
        client = create_client("user-1", service)

        with patch(
            "src.gateway.routers.chat._generate_chat_response",
            AsyncMock(return_value="assistant reply"),
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
            "src.gateway.routers.chat._generate_chat_response",
            AsyncMock(return_value="assistant reply"),
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
            "src.gateway.routers.chat._generate_chat_response",
            AsyncMock(return_value="stream reply"),
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
