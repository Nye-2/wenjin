"""DataService foundation tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.database.base import Base
from src.dataservice.common.api import envelope_error, envelope_ok
from src.dataservice.common.idempotency import IdempotencyScope, make_request_hash, make_scope_hash
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.operations.models import (
    DataServiceIdempotencyKey,
    DataServiceMigrationReport,
    DataServiceOutboxEvent,
)
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagesRebuildPayload,
)
from src.dataservice_client.contracts.execution import (
    ComputeSessionEnsurePayload,
    ComputeSessionUpdatePayload,
)
from src.dataservice_client.contracts.workspace import WorkspaceCreatePayload, WorkspaceUpdatePayload


def test_operations_models_are_registered_on_shared_metadata() -> None:
    assert DataServiceIdempotencyKey.__tablename__ in Base.metadata.tables
    assert DataServiceOutboxEvent.__tablename__ in Base.metadata.tables
    assert DataServiceMigrationReport.__tablename__ in Base.metadata.tables


def test_response_envelope_contract() -> None:
    assert envelope_ok({"value": 1}, trace_id="trace-1") == {
        "status": "ok",
        "data": {"value": 1},
        "trace_id": "trace-1",
    }
    assert envelope_error(code="x", message="failed") == {
        "status": "error",
        "error": {"code": "x", "message": "failed"},
    }


def test_idempotency_hashes_are_stable_and_sensitive_to_scope() -> None:
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    assert make_request_hash(payload_a) == make_request_hash(payload_b)

    base = IdempotencyScope(
        source_service="gateway",
        command_name="workspace.create",
        workspace_id="workspace-1",
        actor_user_id="user-1",
    )
    other_actor = base.model_copy(update={"actor_user_id": "user-2"})
    assert make_scope_hash(base) != make_scope_hash(other_actor)


def test_livez_endpoint_does_not_require_database() -> None:
    from src.dataservice_app.routers.health import router

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "dataservice"}


def test_internal_auth_uses_stable_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.dataservice.common.errors import DataServiceError
    from src.dataservice_app import auth as auth_module
    from src.dataservice_app.app import handle_dataservice_error

    monkeypatch.setattr(auth_module.dataservice_settings, "internal_token", "expected")

    app = FastAPI()
    app.add_exception_handler(DataServiceError, handle_dataservice_error)

    @app.get("/protected")
    async def protected(_: None = Depends(auth_module.require_internal_token)) -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/protected", headers={"X-Wenjin-Internal-Token": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED_INTERNAL_CALL"


@pytest.mark.asyncio
async def test_uow_rolls_back_when_not_committed() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False
            self.closed = False
            self.added: list[Any] = []

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def close(self) -> None:
            self.closed = True

        def add(self, value: Any) -> None:
            self.added.append(value)

    session = FakeSession()

    async with DataServiceUnitOfWork(session=session):  # type: ignore[arg-type]
        pass

    assert session.rolled_back is True
    assert session.committed is False
    assert session.closed is False


@pytest.mark.asyncio
async def test_dataservice_client_sends_internal_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Wenjin-Internal-Token"] == "secret"
        return httpx.Response(200, json={"status": "ok", "data": {"received": True}})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        result = await client._request("GET", "/protected")

    assert result == {"status": "ok", "data": {"received": True}}


@pytest.mark.asyncio
async def test_dataservice_client_workspace_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def workspace_payload(workspace_id: str = "workspace-1") -> dict[str, Any]:
        return {
            "id": workspace_id,
            "created_by_user_id": "user-1",
            "name": "Workspace",
            "workspace_type": "thesis",
            "settings_json": {"language": "zh"},
            "active_thread_id": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": workspace_payload()})
        if request.method == "GET" and request.url.path == "/internal/v1/workspaces":
            return httpx.Response(200, json={"status": "ok", "data": [workspace_payload()]})
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": workspace_payload("workspace-2")})
        if request.method == "PUT":
            payload = workspace_payload("workspace-2")
            payload["name"] = body["name"] if body else "Updated"
            return httpx.Response(200, json={"status": "ok", "data": payload})
        return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_workspace(
            WorkspaceCreatePayload(
                created_by_user_id="user-1",
                name="Workspace",
                workspace_type="thesis",
                settings_json={"language": "zh"},
            )
        )
        listed = await client.list_workspaces(member_user_id="user-1")
        fetched = await client.get_workspace("workspace-2")
        updated = await client.update_workspace(
            "workspace-2",
            WorkspaceUpdatePayload(name="Updated"),
        )
        deleted = await client.delete_workspace("workspace-2")

    assert created.workspace_type == "thesis"
    assert listed[0].id == "workspace-1"
    assert fetched is not None
    assert fetched.id == "workspace-2"
    assert updated is not None
    assert updated.name == "Updated"
    assert deleted is True
    assert seen == [
        (
            "POST",
            "/internal/v1/workspaces",
            {
                "created_by_user_id": "user-1",
                "name": "Workspace",
                "workspace_type": "thesis",
                "discipline": None,
                "description": None,
                "settings_json": {"language": "zh"},
            },
        ),
        ("GET", "/internal/v1/workspaces", None),
        ("GET", "/internal/v1/workspaces/workspace-2", None),
        (
            "PUT",
            "/internal/v1/workspaces/workspace-2",
            {"name": "Updated"},
        ),
        ("DELETE", "/internal/v1/workspaces/workspace-2", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_conversation_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def message_payload(message_id: str = "message-1") -> dict[str, Any]:
        return {
            "id": message_id,
            "thread_id": "thread-1",
            "user_id": "user-1",
            "workspace_id": "ws-1",
            "role": "assistant",
            "content": "Hello",
            "sequence_index": 0,
            "metadata_json": {},
            "blocks": [
                {
                    "id": "block-1",
                    "message_id": message_id,
                    "thread_id": "thread-1",
                    "block_type": "text",
                    "sequence_index": 0,
                    "payload_json": {"kind": "text", "content": "Hello"},
                }
            ],
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": message_payload("message-1")})
        return httpx.Response(200, json={"status": "ok", "data": [message_payload("message-2")]})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        appended = await client.append_conversation_message(
            "thread-1",
            ConversationMessageCreatePayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                role="assistant",
                content="Hello",
                sequence_index=0,
                blocks=[{"kind": "text", "content": "Hello"}],
            ),
        )
        rebuilt = await client.rebuild_conversation_messages(
            "thread-1",
            ConversationMessagesRebuildPayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                messages=[{"role": "assistant", "content": "Hello"}],
            ),
        )
        listed = await client.list_conversation_messages("thread-1")

    assert appended is not None
    assert appended.blocks[0].block_type == "text"
    assert rebuilt[0].id == "message-2"
    assert listed[0].thread_id == "thread-1"
    assert seen[0][0] == "POST"
    assert seen[1][0] == "PUT"
    assert seen[2] == ("GET", "/internal/v1/conversations/thread-1/messages", None)


@pytest.mark.asyncio
async def test_dataservice_client_compute_session_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def session_payload(session_id: str = "compute-1") -> dict[str, Any]:
        return {
            "id": session_id,
            "execution_id": "exec-1",
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "sandbox_session_id": "sandbox-1",
            "active_view": "overview",
            "ui_state": {},
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": {"session": session_payload(), "changed": True}})
        if request.method == "GET" and request.url.path.endswith("/list"):
            return httpx.Response(200, json={"status": "ok", "data": [session_payload()]})
        if request.method == "PATCH":
            payload = session_payload()
            payload["active_view"] = body["active_view"] if body else "files"
            return httpx.Response(200, json={"status": "ok", "data": payload})
        return httpx.Response(200, json={"status": "ok", "data": session_payload("compute-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        ensured, changed = await client.ensure_compute_session(
            ComputeSessionEnsurePayload(
                execution_id="exec-1",
                workspace_id="ws-1",
                user_id="user-1",
                sandbox_session_id="sandbox-1",
            )
        )
        fetched = await client.get_compute_session("compute-2")
        by_execution = await client.get_compute_session_by_execution("exec-1")
        listed = await client.list_compute_sessions(workspace_id="ws-1", user_id="user-1")
        updated = await client.update_compute_session(
            "compute-1",
            ComputeSessionUpdatePayload(active_view="files"),
        )

    assert ensured.id == "compute-1"
    assert changed is True
    assert fetched is not None and fetched.id == "compute-2"
    assert by_execution is not None and by_execution.execution_id == "exec-1"
    assert listed[0].workspace_id == "ws-1"
    assert updated is not None and updated.active_view == "files"
    assert seen == [
        (
            "POST",
            "/internal/v1/executions/compute-sessions/ensure",
            {
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "sandbox_session_id": "sandbox-1",
            },
        ),
        ("GET", "/internal/v1/executions/compute-sessions/compute-2", None),
        ("GET", "/internal/v1/executions/compute-sessions/by-execution/exec-1", None),
        ("GET", "/internal/v1/executions/compute-sessions/list", None),
        ("PATCH", "/internal/v1/executions/compute-sessions/compute-1", {"active_view": "files"}),
    ]
