"""Unit tests for workspace room routes through the DataService client."""

from __future__ import annotations

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
        "authors_json": ["Researcher A", "Researcher B"],
        "ingest_label": "execution:run-1",
        "is_deleted": False,
    }
    values.update(overrides)
    return _fake_row(**values)


def _make_dataservice() -> MagicMock:
    dataservice = MagicMock()
    dataservice.list_sources = AsyncMock(return_value=[])
    dataservice.create_source = AsyncMock()
    dataservice.get_source = AsyncMock(return_value=None)
    dataservice.delete_source = AsyncMock(return_value=False)
    dataservice.list_room_decisions = AsyncMock(return_value=[])
    dataservice.set_room_decision = AsyncMock()
    dataservice.delete_room_decision = AsyncMock(return_value=False)
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
        assert resp.json()["items"][0]["authors"] == ["Researcher A", "Researcher B"]
        assert resp.json()["items"][0]["added_by"] == "execution:run-1"
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


class TestDecisionsRoom:
    def test_list_decisions_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_room_decisions.return_value = [
            _fake_row(
                id="dec-1",
                workspace_id=WS_ID,
                key="citation_style",
                value="IEEE",
                confidence=1.0,
                extracted_by="user",
                created_at=None,
            )
        ]

        resp = client.get(f"/workspaces/{WS_ID}/decisions")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["id"] == "dec-1"
        assert resp.json()["items"][0]["key"] == "citation_style"
        assert resp.json()["items"][0]["value"] == "IEEE"

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


class TestRemovedRooms:
    def test_documents_room_routes_are_removed(self) -> None:
        _app, client, _dataservice = _make_app()

        assert client.get(f"/workspaces/{WS_ID}/documents").status_code == 404
        assert client.post(f"/workspaces/{WS_ID}/documents", json={}).status_code == 404

    def test_memory_room_routes_are_removed(self) -> None:
        _app, client, _dataservice = _make_app()

        assert client.get(f"/workspaces/{WS_ID}/memory").status_code == 404
        assert client.post(f"/workspaces/{WS_ID}/memory", json={}).status_code == 404


class TestTasksRoom:
    def test_list_tasks_happy(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.list_room_tasks.return_value = [_fake_row(id="task-1", workspace_id=WS_ID, title="Do X", status="pending")]

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
            reasoning_effort="xhigh",
        )

        resp = client.get(f"/workspaces/{WS_ID}/settings")

        assert resp.status_code == 200
        assert resp.json()["workspace_id"] == WS_ID

    def test_put_settings_workspace_not_found(self) -> None:
        _app, client, _dataservice = _make_app(workspace_exists=False)

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"reasoning_effort": "low"})

        assert resp.status_code == 404

    def test_put_settings_accepts_review_mode(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.update_workspace_settings.return_value = _fake_row(
            workspace_id=WS_ID,
            review_mode="review_all",
            settings_json={"review_mode": "review_all", "language": "zh"},
        )

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"review_mode": "review_all"})

        assert resp.status_code == 200
        assert resp.json()["review_mode"] == "review_all"
        payload = dataservice.update_workspace_settings.await_args.args[1]
        assert payload.review_mode == "review_all"

    def test_put_settings_trims_review_mode(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.update_workspace_settings.return_value = _fake_row(
            workspace_id=WS_ID,
            review_mode="auto_draft",
            settings_json={"review_mode": "auto_draft"},
        )

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"review_mode": " auto_draft "})

        assert resp.status_code == 200
        payload = dataservice.update_workspace_settings.await_args.args[1]
        assert payload.review_mode == "auto_draft"

    def test_put_settings_review_mode_null_is_omitted(self) -> None:
        _app, client, dataservice = _make_app()
        dataservice.update_workspace_settings.return_value = _fake_row(
            workspace_id=WS_ID,
            review_mode="review_all",
            settings_json={"review_mode": "review_all"},
        )

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"review_mode": None})

        assert resp.status_code == 200
        payload = dataservice.update_workspace_settings.await_args.args[1]
        assert "review_mode" not in payload.model_fields_set
        assert payload.review_mode is None

    def test_put_settings_rejects_invalid_review_mode(self) -> None:
        _app, client, dataservice = _make_app()

        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"review_mode": "manual_review"})

        assert resp.status_code == 422
        dataservice.update_workspace_settings.assert_not_awaited()
