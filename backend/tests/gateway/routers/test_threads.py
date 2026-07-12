"""Tests for platform-style thread search/state/history endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import threads
from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunStatus


@dataclass
class _FakeThread:
    id: str
    user_id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None = None
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeThreadService:
    def __init__(self) -> None:
        self._threads: dict[str, _FakeThread] = {}
        self._canonical_messages: dict[str, list[dict]] = {}

    def add(self, thread: _FakeThread) -> None:
        self._threads[thread.id] = thread
        self._canonical_messages[thread.id] = list(thread.messages)

    def set_canonical_messages(self, thread_id: str, messages: list[dict]) -> None:
        self._canonical_messages[thread_id] = list(messages)

    async def get_thread(self, thread_id: str, user_id: str) -> _FakeThread | None:
        thread = self._threads.get(thread_id)
        if thread is None or thread.user_id != user_id:
            return None
        return thread

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[_FakeThread]:
        items = [thread for thread in self._threads.values() if thread.user_id == user_id and (workspace_id is None or thread.workspace_id == workspace_id)]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[:limit]

    async def list_thread_messages(self, thread: _FakeThread) -> list[dict]:
        return list(self._canonical_messages.get(thread.id, []))


def _create_client(service: _FakeThreadService, run_manager: ChatTurnRunManager) -> TestClient:
    app = FastAPI()

    async def _override_user():
        user = MagicMock()
        user.id = "user-1"
        return user

    async def _override_service():
        return service

    async def _override_run_manager():
        return run_manager

    app.dependency_overrides[threads.get_current_user] = _override_user
    app.dependency_overrides[threads.get_thread_service] = _override_service
    app.dependency_overrides[threads.get_chat_turn_run_manager] = _override_run_manager
    app.include_router(threads.router)
    return TestClient(app)


def test_search_threads_filters_by_metadata_and_status():
    service = _FakeThreadService()
    service.add(
        _FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="A",
            model="tool-a",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    service.add(
        _FakeThread(
            id="thread-2",
            user_id="user-1",
            workspace_id="ws-2",
            title="B",
            model="tool-a",
            messages=[{"role": "user", "content": "world"}],
        )
    )
    run_manager = ChatTurnRunManager()
    client = _create_client(service, run_manager)

    async def _mark_busy() -> None:
        run = await run_manager.create_or_reject("thread-1")
        await run_manager.set_status(run.run_id, ChatTurnRunStatus.running)

    import asyncio

    asyncio.run(_mark_busy())

    response = client.post(
        "/threads/search",
        json={"metadata": {"workspace_id": "ws-1"}, "status": "busy"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["thread_id"] == "thread-1"
    assert payload[0]["status"] == "busy"


def test_get_thread_state_contains_values_and_active_tasks():
    service = _FakeThreadService()
    service.add(
        _FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="State Thread",
            model="tool-a",
            skill="deep-research",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )
    )
    service.set_canonical_messages(
        "thread-1",
        [
            {"role": "user", "content": "canonical hello"},
            {"role": "assistant", "content": "canonical hi"},
        ],
    )
    run_manager = ChatTurnRunManager()
    client = _create_client(service, run_manager)

    async def _mark_busy() -> None:
        run = await run_manager.create_or_reject("thread-1")
        await run_manager.set_status(run.run_id, ChatTurnRunStatus.running)

    import asyncio

    asyncio.run(_mark_busy())

    response = client.get("/threads/thread-1/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["values"]["thread_id"] == "thread-1"
    assert payload["values"]["workspace_id"] == "ws-1"
    assert payload["values"]["skill"] == "deep-research"
    assert payload["values"]["messages"][0]["content"] == "canonical hello"
    assert payload["next"] == ["run"]
    assert payload["tasks"]
    assert payload["tasks"][0]["status"] == "running"


def test_get_thread_history_returns_synthetic_checkpoint_entry():
    service = _FakeThreadService()
    service.add(
        _FakeThread(
            id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            title="History Thread",
            model="tool-a",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    service.set_canonical_messages("thread-1", [{"role": "user", "content": "canonical hello"}])
    client = _create_client(service, ChatTurnRunManager())

    response = client.post("/threads/thread-1/history", json={})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["checkpoint_id"].startswith("thread:thread-1:")
    assert payload[0]["values"]["thread_id"] == "thread-1"
    assert payload[0]["values"]["messages"][0]["content"] == "canonical hello"
