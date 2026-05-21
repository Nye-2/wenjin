"""Unit tests for workspace_rooms router — Option A (mocked services).

Each room gets 1 happy-path test + 1 not-found test.
Services and ownership check are injected via FastAPI dependency overrides.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_workspace_service
from src.gateway.routers import workspace_rooms

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

USER_ID = "user-test-1"
WS_ID = "ws-test-1"


def _make_user(user_id: str = USER_ID) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    return u


def _make_workspace(ws_id: str = WS_ID, user_id: str = USER_ID) -> SimpleNamespace:
    return SimpleNamespace(id=ws_id, user_id=user_id)


def _make_app(*, workspace_exists: bool = True) -> tuple[FastAPI, TestClient]:
    """Create a minimal app with dependency overrides for room tests."""
    app = FastAPI()

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

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_workspace_service] = override_ws_service
    app.include_router(workspace_rooms.router)
    return app, TestClient(app)


# ---------------------------------------------------------------------------
# Helper: fake row object (simulates SQLAlchemy ORM row)
# ---------------------------------------------------------------------------


def _fake_row(**kwargs: object) -> SimpleNamespace:
    ns = SimpleNamespace(**kwargs)
    # No leading underscore attrs — _row_to_dict uses __dict__
    return ns


# ===========================================================================
# LIBRARY
# ===========================================================================


class TestLibraryRoom:
    def test_list_library_happy(self) -> None:
        app, client = _make_app()
        fake_item = _fake_row(id="lib-1", workspace_id=WS_ID, title="Paper A")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.list = AsyncMock(return_value=[fake_item])
            mp.setattr(workspace_rooms, "_library_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/library")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == "lib-1"

    def test_create_library_item_returns_201(self) -> None:
        app, client = _make_app()
        fake_item = _fake_row(id="lib-2", workspace_id=WS_ID, title="Book B", item_type="book")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.add = AsyncMock(return_value=fake_item)
            mp.setattr(workspace_rooms, "_library_service", lambda db: mock_svc)
            resp = client.post(
                f"/workspaces/{WS_ID}/library",
                json={"item_type": "book", "title": "Book B", "added_by": "user"},
            )

        assert resp.status_code == 201
        assert resp.json()["id"] == "lib-2"

    def test_get_library_item_happy(self) -> None:
        app, client = _make_app()
        fake_item = _fake_row(
            id="lib-3",
            workspace_id=WS_ID,
            title="Paper C",
            abstract="Structured summary",
        )

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.get = AsyncMock(return_value=fake_item)
            mp.setattr(workspace_rooms, "_library_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/library/lib-3")

        assert resp.status_code == 200
        assert resp.json()["id"] == "lib-3"
        assert resp.json()["abstract"] == "Structured summary"

    def test_delete_library_not_found(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.delete = AsyncMock(return_value=False)
            mp.setattr(workspace_rooms, "_library_service", lambda db: mock_svc)
            resp = client.delete(f"/workspaces/{WS_ID}/library/nonexistent")

        assert resp.status_code == 404


# ===========================================================================
# DOCUMENTS
# ===========================================================================


class TestDocumentsRoom:
    def test_list_documents_happy(self) -> None:
        app, client = _make_app()
        fake_doc = _fake_row(id="doc-1", workspace_id=WS_ID, name="Intro", kind="draft")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.list = AsyncMock(return_value=[fake_doc])
            mp.setattr(workspace_rooms, "_documents_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/documents")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["id"] == "doc-1"

    def test_create_document_returns_201(self) -> None:
        app, client = _make_app()
        fake_doc = _fake_row(id="doc-2", workspace_id=WS_ID, name="Chapter 1", kind="draft")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.add = AsyncMock(return_value=fake_doc)
            mp.setattr(workspace_rooms, "_documents_service", lambda db: mock_svc)
            resp = client.post(
                f"/workspaces/{WS_ID}/documents",
                json={"name": "Chapter 1", "kind": "draft", "added_by": "user"},
            )

        assert resp.status_code == 201
        assert resp.json()["id"] == "doc-2"

    def test_get_document_happy(self) -> None:
        app, client = _make_app()
        fake_doc = _fake_row(
            id="doc-3",
            workspace_id=WS_ID,
            name="Outline",
            kind="outline",
            metadata_json={"content": "# Intro"},
        )

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.get = AsyncMock(return_value=fake_doc)
            mp.setattr(workspace_rooms, "_documents_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/documents/doc-3")

        assert resp.status_code == 200
        assert resp.json()["id"] == "doc-3"
        assert resp.json()["metadata_json"]["content"] == "# Intro"

    def test_get_doc_not_found_on_delete(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.delete = AsyncMock(return_value=False)
            mp.setattr(workspace_rooms, "_documents_service", lambda db: mock_svc)
            resp = client.delete(f"/workspaces/{WS_ID}/documents/missing-doc")

        assert resp.status_code == 404


# ===========================================================================
# DECISIONS
# ===========================================================================


class TestDecisionsRoom:
    def test_list_decisions_happy(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.get_active = AsyncMock(return_value={"citation_style": "IEEE"})
            mp.setattr(workspace_rooms, "_decisions_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/decisions")

        assert resp.status_code == 200
        assert resp.json()["active"]["citation_style"] == "IEEE"

    def test_set_decision_returns_201(self) -> None:
        app, client = _make_app()
        fake_decision = _fake_row(
            id="dec-1",
            workspace_id=WS_ID,
            key="citation_style",
            value="APA",
        )

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.set = AsyncMock(return_value=fake_decision)
            mp.setattr(workspace_rooms, "_decisions_service", lambda db: mock_svc)
            resp = client.post(
                f"/workspaces/{WS_ID}/decisions",
                json={"key": "citation_style", "value": "APA", "extracted_by": "user"},
            )

        assert resp.status_code == 201
        assert resp.json()["id"] == "dec-1"

    def test_delete_decision_not_found(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.delete = AsyncMock(return_value=False)
            mp.setattr(workspace_rooms, "_decisions_service", lambda db: mock_svc)
            resp = client.delete(f"/workspaces/{WS_ID}/decisions/nope")

        assert resp.status_code == 404


# ===========================================================================
# MEMORY
# ===========================================================================


class TestMemoryRoom:
    def test_list_memory_happy(self) -> None:
        app, client = _make_app()
        fake_fact = _fake_row(id="fact-1", workspace_id=WS_ID, category="pref", content="IEEE")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.top = AsyncMock(return_value=[fake_fact])
            mp.setattr(workspace_rooms, "_memory_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/memory")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_add_memory_facts_returns_201(self) -> None:
        app, client = _make_app()
        fake_fact = _fake_row(id="fact-2", workspace_id=WS_ID, category="pref", content="APA")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.add_facts = AsyncMock(return_value=[fake_fact])

            import src.services.rooms.memory_service as mem_mod

            mp.setattr(workspace_rooms, "_memory_service", lambda db: mock_svc)
            mp.setattr(mem_mod, "FactCreate", mem_mod.FactCreate)
            resp = client.post(
                f"/workspaces/{WS_ID}/memory",
                json={"facts": [{"category": "pref", "content": "APA"}]},
            )

        assert resp.status_code == 201
        assert resp.json()["count"] == 1

    def test_delete_memory_fact_not_found(self) -> None:
        """Returns 404 when the memory fact doesn't exist in DB."""
        from unittest.mock import patch

        app, client = _make_app()

        # Patch the DB query inside the delete endpoint directly
        with patch(
            "src.gateway.routers.workspace_rooms.AsyncSession",
            autospec=True,
        ):
            # We need to override the DB dependency to use an AsyncMock that returns None
            from src.gateway.deps import get_db

            async def override_db():  # type: ignore
                mock_db = AsyncMock()
                # scalars().scalar_one_or_none() -> None (simulates not found)
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)
                yield mock_db

            app.dependency_overrides[get_db] = override_db
            resp = client.delete(f"/workspaces/{WS_ID}/memory/missing-fact")
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404


# ===========================================================================
# RUNS
# ===========================================================================


class TestRunsRoom:
    def test_list_runs_happy(self) -> None:
        app, client = _make_app()
        fake_run = _fake_row(id="run-1", workspace_id=WS_ID, title="Run 1", status="completed")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.list_run_history = AsyncMock(return_value=[fake_run])
            mp.setattr(workspace_rooms, "_execution_history_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/runs")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["id"] == "run-1"

    def test_get_run_not_found(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.get_run_history_item = AsyncMock(return_value=None)
            mp.setattr(workspace_rooms, "_execution_history_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/runs/nonexistent")

        assert resp.status_code == 404


# ===========================================================================
# TASKS
# ===========================================================================


class TestTasksRoom:
    def test_list_tasks_happy(self) -> None:
        app, client = _make_app()
        fake_task = _fake_row(id="task-1", workspace_id=WS_ID, title="Do X", status="pending")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.list = AsyncMock(return_value=[fake_task])
            mp.setattr(workspace_rooms, "_workspace_tasks_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/tasks")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["id"] == "task-1"

    def test_create_task_returns_201(self) -> None:
        app, client = _make_app()
        fake_task = _fake_row(id="task-2", workspace_id=WS_ID, title="Do Y", status="pending")

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.add = AsyncMock(return_value=fake_task)
            mp.setattr(workspace_rooms, "_workspace_tasks_service", lambda db: mock_svc)
            resp = client.post(
                f"/workspaces/{WS_ID}/tasks",
                json={"title": "Do Y", "created_by": "user"},
            )

        assert resp.status_code == 201
        assert resp.json()["id"] == "task-2"

    def test_delete_task_not_found(self) -> None:
        app, client = _make_app()

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.delete = AsyncMock(return_value=False)
            mp.setattr(workspace_rooms, "_workspace_tasks_service", lambda db: mock_svc)
            resp = client.delete(f"/workspaces/{WS_ID}/tasks/missing")

        assert resp.status_code == 404


# ===========================================================================
# SETTINGS
# ===========================================================================


class TestSettingsRoom:
    def test_get_settings_happy(self) -> None:
        app, client = _make_app()
        fake_settings = _fake_row(
            workspace_id=WS_ID,
            thinking_enabled=True,
            sandbox_provider="local",
        )

        with pytest.MonkeyPatch.context() as mp:
            mock_svc = MagicMock()
            mock_svc.get_or_create = AsyncMock(return_value=fake_settings)
            mp.setattr(workspace_rooms, "_settings_service", lambda db: mock_svc)
            resp = client.get(f"/workspaces/{WS_ID}/settings")

        assert resp.status_code == 200
        assert resp.json()["workspace_id"] == WS_ID

    def test_put_settings_workspace_not_found(self) -> None:
        _app, client = _make_app(workspace_exists=False)
        resp = client.put(f"/workspaces/{WS_ID}/settings", json={"thinking_enabled": False})
        assert resp.status_code == 404


# ===========================================================================
# SANDBOX exec
# ===========================================================================


class TestSandboxExecRoom:
    def test_exec_happy(self) -> None:
        app, client = _make_app()
        fake_sandbox = _fake_row(
            sandbox_id="sbx-1",
            provider="local",
            state="active",
        )

        from unittest.mock import patch

        with patch("src.services.rooms.sandbox_service.SandboxService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_or_create = AsyncMock(return_value=fake_sandbox)
            instance.touch = AsyncMock(return_value=fake_sandbox)

            with pytest.MonkeyPatch.context() as mp:
                from src.services.rooms import sandbox_service as sb_mod

                mp.setattr(sb_mod, "SandboxService", MockSvc)
                resp = client.post(
                    f"/workspaces/{WS_ID}/sandbox/exec",
                    json={"command": "echo hello"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["command"] == "echo hello"
        assert data["status"] == "queued"

    def test_exec_workspace_not_found(self) -> None:
        _app, client = _make_app(workspace_exists=False)
        resp = client.post(
            f"/workspaces/{WS_ID}/sandbox/exec",
            json={"command": "ls"},
        )
        assert resp.status_code == 404
