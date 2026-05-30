"""Tests for run lifecycle thread endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.handlers.thread_turn_handler import ThreadStreamDelta
from src.application.results import CompletedThreadTurn, GeneratedThreadReply, PreparedThreadTurn
from src.gateway.routers import runs, thread_runs
from src.runtime.runs import DisconnectMode, RunManager, RunRecord, RunStatus, run_thread_turn
from src.runtime.stream_bridge import MemoryStreamBridge
from src.task.tasks.run import _build_turn_request


class _FakeThreadService:
    def __init__(self) -> None:
        self._threads: dict[str, tuple[SimpleNamespace, str]] = {}
        self._canonical_messages: dict[str, list[dict[str, Any]]] = {}

    def upsert(self, thread: SimpleNamespace, *, owner_id: str) -> None:
        self._threads[str(thread.id)] = (thread, str(owner_id))
        self._canonical_messages[str(thread.id)] = list(thread.messages or [])

    async def get_thread(self, thread_id: str, user_id: str):
        resolved = self._threads.get(str(thread_id))
        if resolved is None:
            return None
        thread, owner_id = resolved
        return thread if owner_id == str(user_id) else None

    async def list_thread_messages(self, thread: SimpleNamespace) -> list[dict[str, Any]]:
        return list(self._canonical_messages.get(str(thread.id), []))


@dataclass
class _FakeStreamRun:
    chunks: list[ThreadStreamDelta]
    completed: CompletedThreadTurn

    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self) -> CompletedThreadTurn:
        return self.completed


class _FakeHandler:
    def __init__(self) -> None:
        self.thread_service = _FakeThreadService()

    async def preflight_stream_turn(self, _request, *, actor_id: str) -> None:
        assert actor_id == "user-1"

    async def prepare_turn(self, request, *, actor_id: str):
        assert actor_id == "user-1"
        thread = SimpleNamespace(
            id=request.thread_id or "generated-thread",
            workspace_id=request.workspace_id,
            title="Run thread",
            model=request.model or "default",
            skill=request.skill,
            messages=[
                {
                    "role": "user",
                    "content": request.message,
                    "timestamp": "2026-04-14T00:00:00+00:00",
                },
                {
                    "role": "assistant",
                    "content": "hello",
                    "timestamp": "2026-04-14T00:00:00+00:00",
                    "blocks": [],
                    "metadata": {},
                },
            ],
        )
        self.thread_service.upsert(thread, owner_id=actor_id)
        return PreparedThreadTurn(request=request, thread=thread)

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str):
        assert actor_id == "user-1"
        reply = GeneratedThreadReply(content="hello")
        completed = CompletedThreadTurn(
            thread=prepared.thread,
            assistant_message={
                "role": "assistant",
                "content": "hello",
                "timestamp": "2026-04-14T00:00:00+00:00",
                "blocks": [],
                "metadata": {},
            },
            reply=reply,
        )
        return _FakeStreamRun(
            chunks=[ThreadStreamDelta(kind="content", text="hello")],
            completed=completed,
        )


class _FakeExecuteRunTask:
    def __init__(
        self,
        *,
        run_manager: RunManager,
        bridge: MemoryStreamBridge,
        handler: _FakeHandler,
    ) -> None:
        self._run_manager = run_manager
        self._bridge = bridge
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    def apply_async(self, *, args: list[Any], queue: str):
        self.calls.append({"args": list(args), "queue": queue})
        run_id = str(args[0])
        request_payload = args[1] if isinstance(args[1], dict) else {}
        actor_id = str(args[2])

        async def _worker_run() -> None:
            record = await self._run_manager.get_or_load(run_id)
            if record is None:
                return
            request = _build_turn_request(request_payload)
            await run_thread_turn(
                self._bridge,
                self._run_manager,
                record,
                handler=self._handler,  # type: ignore[arg-type]
                request=request,
                actor_id=actor_id,
            )

        asyncio.get_running_loop().create_task(_worker_run())
        return SimpleNamespace(id=f"fake-worker-{len(self.calls)}")


def _create_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_id: str = "user-1",
    shared_handler: _FakeHandler | None = None,
    run_manager: RunManager | None = None,
    stream_bridge: MemoryStreamBridge | None = None,
) -> TestClient:
    app = FastAPI()
    shared_handler = shared_handler or _FakeHandler()
    run_manager = run_manager or RunManager()
    stream_bridge = stream_bridge or MemoryStreamBridge(queue_maxsize=64)
    app.state.run_manager = run_manager
    app.state.stream_bridge = stream_bridge

    async def _override_user():
        user = MagicMock()
        user.id = user_id
        return user

    async def _override_handler():
        return shared_handler

    async def _override_thread_service():
        return shared_handler.thread_service

    import src.gateway.services.run_launch as run_launch_module
    import src.gateway.services.run_lifecycle as run_lifecycle_module
    import src.task.tasks as task_module

    async def _allow_workspace_owner(*args, **kwargs):
        workspace_id = kwargs.get("workspace_id")
        return SimpleNamespace(id=workspace_id)

    fake_execute_run = _FakeExecuteRunTask(
        run_manager=run_manager,
        bridge=stream_bridge,
        handler=shared_handler,
    )
    monkeypatch.setattr(
        run_launch_module,
        "require_workspace_owner_by_dataservice",
        _allow_workspace_owner,
    )
    monkeypatch.setattr(run_lifecycle_module.celery_settings, "enabled", True)
    monkeypatch.setattr(run_lifecycle_module.redis_settings, "enabled", True)
    monkeypatch.setattr(task_module, "execute_run", fake_execute_run)

    app.dependency_overrides[thread_runs.get_current_user] = _override_user
    app.dependency_overrides[thread_runs.get_thread_turn_handler] = _override_handler
    app.dependency_overrides[thread_runs.get_thread_service] = _override_thread_service
    app.dependency_overrides[runs.get_current_user] = _override_user
    app.dependency_overrides[runs.get_thread_turn_handler] = _override_handler
    app.dependency_overrides[runs.get_thread_service] = _override_thread_service
    app.include_router(thread_runs.router)
    app.include_router(runs.router)
    return TestClient(app)


def test_thread_run_stream_emits_expected_events(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    response = client.post(
        "/threads/thread-1/runs/stream",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert response.headers["content-location"].startswith("/api/runs/")
    assert response.headers["content-location"].endswith("/stream")
    assert "event: thread_id" in response.text
    assert "event: content" in response.text
    # Spec §5.2 — assistant_message replaced by per-block events
    assert "event: block" in response.text
    assert "event: assistant_message" not in response.text
    assert "event: done" in response.text
    assert "event: end" in response.text


def test_thread_run_create_and_get(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    created = client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    assert created.status_code == 200
    payload = created.json()
    run_id = payload["run_id"]

    fetched = client.get(f"/threads/thread-1/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_id

    listed = client.get("/threads/thread-1/runs")
    assert listed.status_code == 200
    ids = [item["run_id"] for item in listed.json()]
    assert run_id in ids


def test_run_id_stream_endpoint_replays_existing_run(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    created = client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    run_id = created.json()["run_id"]

    resumed = client.get(f"/runs/{run_id}/stream")
    assert resumed.status_code == 200
    assert resumed.headers["content-location"] == f"/api/runs/{run_id}/stream"
    assert "event: thread_id" in resumed.text
    assert "event: done" in resumed.text


def test_thread_scoped_existing_stream_includes_run_content_location(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    created = client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    run_id = created.json()["run_id"]

    resumed = client.get(f"/threads/thread-1/runs/{run_id}/stream")
    assert resumed.status_code == 200
    assert resumed.headers["content-location"] == f"/api/runs/{run_id}/stream"


def test_run_id_get_endpoint_returns_existing_run(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    created = client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    run_id = created.json()["run_id"]

    fetched = client.get(f"/runs/{run_id}")
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["run_id"] == run_id
    assert payload["thread_id"] == "thread-1"


def test_run_id_cancel_endpoint_returns_not_found_for_missing_run(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    response = client.post("/runs/missing-run/cancel")
    assert response.status_code == 404


def test_thread_wait_returns_thread_values_snapshot(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    response = client.post(
        "/threads/thread-1/runs/wait",
        json={"message": "hello", "workspace_id": "ws-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["thread_id"] == "thread-1"
    assert payload["values"]["thread_id"] == "thread-1"
    assert payload["values"]["workspace_id"] == "ws-1"
    assert len(payload["values"]["messages"]) == 2


def test_stateless_wait_returns_thread_values_snapshot(monkeypatch: pytest.MonkeyPatch):
    client = _create_client(monkeypatch)

    response = client.post(
        "/runs/wait",
        json={"message": "hello", "workspace_id": "ws-2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["thread_id"] == "generated-thread"
    assert payload["values"]["thread_id"] == "generated-thread"
    assert payload["values"]["workspace_id"] == "ws-2"
    assert payload["values"]["messages"][1]["role"] == "assistant"


def test_run_id_endpoints_require_run_owner(monkeypatch: pytest.MonkeyPatch):
    shared_handler = _FakeHandler()
    run_manager = RunManager()
    stream_bridge = MemoryStreamBridge(queue_maxsize=64)

    owner_client = _create_client(
        monkeypatch,
        user_id="user-1",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )
    intruder_client = _create_client(
        monkeypatch,
        user_id="user-2",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )

    created = owner_client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    get_response = intruder_client.get(f"/runs/{run_id}")
    assert get_response.status_code == 404

    cancel_response = intruder_client.post(f"/runs/{run_id}/cancel")
    assert cancel_response.status_code == 404

    stream_response = intruder_client.get(f"/runs/{run_id}/stream")
    assert stream_response.status_code == 404


def test_thread_scoped_run_endpoints_require_thread_owner(monkeypatch: pytest.MonkeyPatch):
    shared_handler = _FakeHandler()
    run_manager = RunManager()
    stream_bridge = MemoryStreamBridge(queue_maxsize=64)

    owner_client = _create_client(
        monkeypatch,
        user_id="user-1",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )
    intruder_client = _create_client(
        monkeypatch,
        user_id="user-2",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )

    created = owner_client.post(
        "/threads/thread-1/runs",
        json={"message": "hello"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    list_response = intruder_client.get("/threads/thread-1/runs")
    assert list_response.status_code == 404

    get_response = intruder_client.get(f"/threads/thread-1/runs/{run_id}")
    assert get_response.status_code == 404

    cancel_response = intruder_client.post(f"/threads/thread-1/runs/{run_id}/cancel")
    assert cancel_response.status_code == 404


def test_run_id_owner_metadata_allows_owner_before_thread_binding(
    monkeypatch: pytest.MonkeyPatch,
):
    shared_handler = _FakeHandler()
    run_manager = RunManager()
    stream_bridge = MemoryStreamBridge(queue_maxsize=64)
    run_id = "run-prebind-owner"
    run_manager._runs[run_id] = RunRecord(
        run_id=run_id,
        thread_id="placeholder-thread",
        assistant_id="thread",
        status=RunStatus.pending,
        on_disconnect=DisconnectMode.continue_,
        metadata={"_owner_id": "user-1"},
    )

    owner_client = _create_client(
        monkeypatch,
        user_id="user-1",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )
    intruder_client = _create_client(
        monkeypatch,
        user_id="user-2",
        shared_handler=shared_handler,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )

    owner_get = owner_client.get(f"/runs/{run_id}")
    assert owner_get.status_code == 200
    assert owner_get.json()["run_id"] == run_id
    assert "_owner_id" not in owner_get.json().get("metadata", {})

    intruder_get = intruder_client.get(f"/runs/{run_id}")
    assert intruder_get.status_code == 404
