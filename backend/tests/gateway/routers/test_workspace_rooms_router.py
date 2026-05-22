"""Unit tests for workspace room routes through the DataService client."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_workspace_service
from src.gateway.routers import workspace_rooms

USER_ID = "user-test-1"
WS_ID = "ws-test-1"


def _make_user(user_id: str = USER_ID) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _make_workspace(ws_id: str = WS_ID, user_id: str = USER_ID) -> SimpleNamespace:
    return SimpleNamespace(id=ws_id, user_id=user_id)


def _fake_row(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _fake_source(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "lib-1",
        "workspace_id": WS_ID,
        "title": "Paper A",
        "is_deleted": False,
    }
    values.update(overrides)
    return _fake_row(**values)


def _fake_asset(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "asset-1",
        "workspace_id": WS_ID,
        "asset_kind": "document",
        "name": "Draft",
        "mime_type": "text/markdown",
        "storage_path": "inline://documents/draft",
        "size_bytes": 10,
        "parent_asset_id": None,
        "created_by": "user",
        "source_kind": "documents_room",
        "metadata_json": {"kind": "draft", "version": 1},
        "deleted_at": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return _fake_row(**values)


def _make_dataservice() -> MagicMock:
    dataservice = MagicMock()
    dataservice.list_sources = AsyncMock(return_value=[])
    dataservice.create_source = AsyncMock()
    dataservice.get_source = AsyncMock(return_value=None)
    dataservice.delete_source = AsyncMock(return_value=False)
    dataservice.list_assets = AsyncMock(return_value=[])
    dataservice.get_asset = AsyncMock(return_value=None)
    dataservice.register_asset = AsyncMock()
    dataservice.update_asset = AsyncMock(return_value=None)
    dataservice.delete_asset = AsyncMock(return_value=None)
    dataservice.list_room_decisions = AsyncMock(return_value={})
    dataservice.set_room_decision = AsyncMock()
    dataservice.delete_room_decision = AsyncMock(return_value=False)
    dataservice.list_room_memory_facts = AsyncMock(return_value=[])
    dataservice.add_room_memory_facts = AsyncMock(return_value=[])
    dataservice.delete_room_memory_fact = AsyncMock(return_value=False)
    dataservice.list_executions = AsyncMock(return_value=[])
    dataservice.get_execution = AsyncMock(return_value=None)
    dataservice.list_room_tasks = AsyncMock(return_value=[])
    dataservice.create_room_task = AsyncMock()
    dataservice.update_room_task = AsyncMock(return_value=None)
    dataservice.delete_room_task = AsyncMock(return_value=False)
    dataservice.get_workspace_settings = AsyncMock()
    dataservice.update_workspace_settings = AsyncMock()
    dataservice.get_or_create_sandbox_environment = AsyncMock()
    return dataservice


def _make_app(
    *,
    workspace_exists: bool = True,
    dataservice: MagicMock | None = None,
) -> tuple[FastAPI, TestClient, MagicMock]:
    app = FastAPI()
    fake_dataservice = dataservice or _make_dataservice()

    async def override_user() -> MagicMock:
        return _make_user()

    async def override_ws_service() -> MagicMock:
        svc = MagicMock()
        if workspace_exists:
            svc.get = AsyncMock(return_value=_make_workspace())
            svc.has_active_membership = AsyncMock(return_value=True)
        else:
            svc.get = AsyncMock(return_value=None)
            svc.has_active_membership = AsyncMock(return_value=False)
        return svc

    async def override_dataservice() -> MagicMock:
        return fake_dataservice

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_workspace_service] = override_ws_service
    app.dependency_overrides[workspace_rooms.get_dataservice_client] = override_dataservice
    app.include_router(workspace_rooms.router)
    return app, TestClient(app), fake_dataservice


class TestLibraryRoom:
    def test_list_library_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_sources.return_value = [_fake_source(id="lib-1")]

        resp = client.get(f"/workspaces/{WS_ID}/library")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "lib-1"
        dataservice.list_sources.assert_awaited_once()

    def test_create_library_item_returns_201(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.create_source.return_value = _fake_source(id="lib-2", item_type="book")

        resp = client.post(
            f"/workspaces/{WS_ID}/library",
            json={"item_type": "book", "title": "Book B", "added_by": "user"},
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == "lib-2"

    def test_get_library_item_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_source.return_value = _fake_source(id="lib-3", abstract="Structured summary")

        resp = client.get(f"/workspaces/{WS_ID}/library/lib-3")

        assert resp.status_code == 200
        assert resp.json()["abstract"] == "Structured summary"

    def test_delete_library_not_found(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.delete_source.return_value = False

        resp = client.delete(f"/workspaces/{WS_ID}/library/nonexistent")

        assert resp.status_code == 404


class TestDocumentsRoom:
    def test_list_documents_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_assets.side_effect = [
            [_fake_asset(id="doc-1", name="Intro", metadata_json={"kind": "draft", "version": 1})],
            [],
        ]

        resp = client.get(f"/workspaces/{WS_ID}/documents")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "doc-1"

    def test_create_document_returns_201(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.register_asset.return_value = _fake_asset(id="doc-2", name="Chapter 1")

        resp = client.post(
            f"/workspaces/{WS_ID}/documents",
            json={"name": "Chapter 1", "kind": "draft", "added_by": "user"},
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == "doc-2"

    def test_get_document_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_asset.return_value = _fake_asset(
            id="doc-3",
            name="Outline",
            metadata_json={"kind": "outline", "version": 1, "content": "# Intro"},
        )

        resp = client.get(f"/workspaces/{WS_ID}/documents/doc-3")

        assert resp.status_code == 200
        assert resp.json()["metadata_json"]["content"] == "# Intro"

    def test_get_doc_not_found_on_delete(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_asset.return_value = None

        resp = client.delete(f"/workspaces/{WS_ID}/documents/missing-doc")

        assert resp.status_code == 404

class TestDecisionsRoom:
    def test_list_decisions_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_room_decisions.return_value = {"citation_style": "IEEE"}

        resp = client.get(f"/workspaces/{WS_ID}/decisions")

        assert resp.status_code == 200
        assert resp.json()["active"]["citation_style"] == "IEEE"

    def test_set_decision_returns_201(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.set_room_decision.return_value = _fake_row(
            id="dec-1",
            workspace_id=WS_ID,
            key="citation_style",
            value="APA",
        )

        resp = client.post(
            f"/workspaces/{WS_ID}/decisions",
            json={"key": "citation_style", "value": "APA", "extracted_by": "user"},
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == "dec-1"

    def test_delete_decision_not_found(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.delete_room_decision.return_value = False

        resp = client.delete(f"/workspaces/{WS_ID}/decisions/nope")

        assert resp.status_code == 404


class TestMemoryRoom:
    def test_list_memory_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_room_memory_facts.return_value = [
            _fake_row(id="fact-1", workspace_id=WS_ID, category="pref", content="IEEE")
        ]

        resp = client.get(f"/workspaces/{WS_ID}/memory")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_add_memory_facts_returns_201(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.add_room_memory_facts.return_value = [
            _fake_row(id="fact-2", workspace_id=WS_ID, category="pref", content="APA")
        ]

        resp = client.post(
            f"/workspaces/{WS_ID}/memory",
            json={"facts": [{"category": "pref", "content": "APA"}]},
        )

        assert resp.status_code == 201
        assert resp.json()["count"] == 1

    def test_delete_memory_fact_not_found(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.delete_room_memory_fact.return_value = False

        resp = client.delete(f"/workspaces/{WS_ID}/memory/missing-fact")

        assert resp.status_code == 404


class TestRunsRoom:
    def test_list_runs_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_executions.return_value = [
            _fake_row(
                id="exec-1",
                display_name="文献定位与创新点",
                workspace_id=WS_ID,
                thread_id="thread-1",
                feature_id="sci_literature_positioning",
                execution_type="feature",
                status="completed",
                progress=100,
                started_at=None,
                created_at=datetime.fromisoformat("2026-05-22T09:08:55+00:00"),
                completed_at=datetime.fromisoformat("2026-05-22T09:09:39+00:00"),
                result_summary="完成 文献定位与创新点，共执行 3 个节点。",
                message=None,
                error=None,
                result={
                    "task_report": {
                        "token_usage": {"input_tokens": 10, "output_tokens": 5},
                        "review_items": [
                            {
                                "id": "review-1",
                                "kind": "prism_file_change",
                                "target": {"kind": "prism_file_change"},
                            }
                        ],
                    }
                },
            )
        ]

        resp = client.get(f"/workspaces/{WS_ID}/runs")

        assert resp.status_code == 200
        assert resp.json()["items"] == [
            {
                "id": "exec-1",
                "workspace_id": WS_ID,
                "thread_id": "thread-1",
                "capability_id": "sci_literature_positioning",
                "capability_name": "文献定位与创新点",
                "status": "completed",
                "started_at": "2026-05-22T09:08:55+00:00",
                "completed_at": "2026-05-22T09:09:39+00:00",
                "summary": "完成 文献定位与创新点，共执行 3 个节点。",
                "token_usage": {"input": 10, "output": 5},
                "progress": 100,
                "primary_surface": "prism",
                "review_items_count": 1,
                "has_prism_changes": True,
                "failure_category": None,
                "failure_message": None,
            }
        ]

    def test_get_run_not_found(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_execution.return_value = None

        resp = client.get(f"/workspaces/{WS_ID}/runs/nonexistent")

        assert resp.status_code == 404


class TestTasksRoom:
    def test_list_tasks_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_room_tasks.return_value = [
            _fake_row(id="task-1", workspace_id=WS_ID, title="Do X", status="pending")
        ]

        resp = client.get(f"/workspaces/{WS_ID}/tasks")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "task-1"

    def test_create_task_returns_201(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.create_room_task.return_value = _fake_row(
            id="task-2",
            workspace_id=WS_ID,
            title="Do Y",
            status="pending",
        )

        resp = client.post(f"/workspaces/{WS_ID}/tasks", json={"title": "Do Y", "created_by": "user"})

        assert resp.status_code == 201
        assert resp.json()["id"] == "task-2"

    def test_delete_task_not_found(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.delete_room_task.return_value = False

        resp = client.delete(f"/workspaces/{WS_ID}/tasks/missing")

        assert resp.status_code == 404


class TestSettingsRoom:
    def test_get_settings_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_workspace_settings.return_value = _fake_row(
            workspace_id=WS_ID,
            thinking_enabled=True,
            sandbox_provider="local",
        )

        resp = client.get(f"/workspaces/{WS_ID}/settings")

        assert resp.status_code == 200
        assert resp.json()["workspace_id"] == WS_ID

    def test_put_settings_workspace_not_found(self) -> None:
        _app, client, _dataservice = _make_app(workspace_exists=False)

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"thinking_enabled": False})

        assert resp.status_code == 404


class TestSandboxExecRoom:
    def test_exec_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.get_or_create_sandbox_environment.return_value = _fake_row(
            sandbox_id="sbx-1",
            provider="local",
            state="active",
        )

        resp = client.post(f"/workspaces/{WS_ID}/sandbox/exec", json={"command": "echo hello"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_exec_workspace_not_found(self) -> None:
        _app, client, _dataservice = _make_app(workspace_exists=False)

        resp = client.post(f"/workspaces/{WS_ID}/sandbox/exec", json={"command": "ls"})

        assert resp.status_code == 404
