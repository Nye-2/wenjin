"""Tests for features router."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import WorkspaceType
from src.gateway.routers import features
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.features import ExecuteResponse
from src.services.literature_service import get_literature_service


def create_mock_user(user_id: str) -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = user_id
    return user


def create_workspace(workspace_type, user_id: str = "user-1") -> MagicMock:
    """Create a minimal workspace object for router tests."""
    workspace = MagicMock()
    workspace.id = "ws-1"
    workspace.user_id = user_id
    workspace.name = "Workspace Alpha"
    workspace.type = workspace_type
    workspace.description = "Reusable feature execution test workspace"
    workspace.discipline = "computer_science"
    workspace.config = {"template": "default"}
    return workspace


def create_client(
    user_id: str,
    workspace_service,
    task_service,
    literature_service=None,
) -> TestClient:
    """Create a features test client with dependency overrides."""
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_task_service():
        yield task_service

    async def override_get_literature_service():
        return literature_service or AsyncMock()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[features.get_workspace_service] = (
        override_get_workspace_service
    )
    app.dependency_overrides[features.get_task_service] = override_get_task_service
    app.dependency_overrides[get_literature_service] = override_get_literature_service
    app.include_router(features.router)
    return TestClient(app)


class TestWorkspaceFeaturesRouter:
    """Tests for workspace feature discovery and execution."""

    def test_get_workspace_features_returns_registry_features(self):
        """Feature discovery is driven by the canonical registry."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        client = create_client("user-1", workspace_service, task_service)

        response = client.get("/workspaces/ws-1/features")

        assert response.status_code == 200
        data = response.json()
        assert [feature["id"] for feature in data["features"]] == [
            "deep_research",
            "literature_management",
            "opening_research",
            "thesis_writing",
            "figure_generation",
            "compile_export",
        ]

    def test_get_workspace_features_rejects_other_users_workspace(self):
        """Feature discovery enforces workspace ownership."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SCI, user_id="owner-1")
        )
        task_service = AsyncMock()
        client = create_client("user-2", workspace_service, task_service)

        response = client.get("/workspaces/ws-1/features")

        assert response.status_code == 403

    def test_execute_feature_submits_canonical_task_payload(self):
        """Feature execution uses registry metadata rather than router-local constants."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SOFTWARE_COPYRIGHT)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-123")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/copyright_materials/execute",
            json={
                "params": {"project_name": "Alpha"},
                "thread_id": "thread-9",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "task_id": "task-123",
            "status": "pending",
            "feature_id": "copyright_materials",
            "message": "Queued 材料准备",
            "warning": None,
            "detail": None,
        }

        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["user_id"] == "user-1"
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"] == {
            "workspace_id": "ws-1",
            "workspace_type": "software_copyright",
            "workspace_name": "Workspace Alpha",
            "workspace_description": "Reusable feature execution test workspace",
            "workspace_discipline": "computer_science",
            "workspace_config": {"template": "default"},
            "feature_id": "copyright_materials",
            "feature_name": "材料准备",
            "agent": "writer",
            "agent_label": "Writer",
            "handler_key": "software_copyright.copyright_materials",
            "thread_id": "thread-9",
            "params": {"project_name": "Alpha"},
            "project_name": "Alpha",
        }

    def test_execute_feature_returns_404_for_unknown_feature(self):
        """Unknown feature ids are rejected before task submission."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.PATENT)
        )
        task_service = AsyncMock()
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/unknown/execute",
            json={"params": {}},
        )

        assert response.status_code == 404

    def test_execute_feature_params_cannot_override_canonical_context(self):
        """User params should not overwrite routing-critical task payload fields."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SOFTWARE_COPYRIGHT)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-456")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/copyright_materials/execute",
            json={
                "params": {
                    "workspace_id": "evil-ws",
                    "workspace_type": "thesis",
                    "feature_id": "outline",
                    "handler_key": "thesis.outline",
                    "agent": "thesis_writer",
                    "software_name": "SafeName",
                }
            },
        )

        assert response.status_code == 200
        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["payload"]["workspace_id"] == "ws-1"
        assert submit_kwargs["payload"]["workspace_type"] == "software_copyright"
        assert submit_kwargs["payload"]["feature_id"] == "copyright_materials"
        assert submit_kwargs["payload"]["handler_key"] == (
            "software_copyright.copyright_materials"
        )
        assert submit_kwargs["payload"]["agent"] == "writer"
        assert submit_kwargs["payload"]["software_name"] == "SafeName"


class TestExecuteResponseModel:
    """Tests for ExecuteResponse model with warning support."""

    def test_normal_response(self):
        resp = ExecuteResponse(task_id="t-1", status="pending", feature_id="f-1", message="ok")
        assert resp.task_id == "t-1"
        assert resp.warning is None

    def test_warning_response_without_task_id(self):
        resp = ExecuteResponse(
            task_id=None, status="warning", feature_id="thesis_writing",
            message="Literature insufficient", warning="literature_insufficient",
            detail={"current": 2, "recommended": 15},
        )
        assert resp.task_id is None
        assert resp.warning == "literature_insufficient"
        assert resp.detail["current"] == 2


class TestLiteratureInsufficientWarning:
    """Tests for literature insufficiency warning during thesis writing."""

    def test_thesis_writing_warns_when_literature_insufficient(self):
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-789")

        literature_service = AsyncMock()
        literature_service.count_literature.return_value = {"total": 2, "core": 0}

        # Create client with literature_service override
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[features.get_task_service] = lambda: task_service
        app.dependency_overrides[get_literature_service] = lambda: literature_service
        app.include_router(features.router)
        client = TestClient(app)

        response = client.post(
            "/workspaces/ws-1/features/thesis_writing/execute",
            json={"params": {"action": "write_chapter", "chapter_index": 0}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["warning"] == "literature_insufficient"
        assert data["task_id"] is None
        assert data["detail"]["current"] == 2

    def test_thesis_writing_proceeds_when_literature_sufficient(self):
        """When literature is sufficient, task should be submitted normally."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-789")

        literature_service = AsyncMock()
        literature_service.count_literature.return_value = {"total": 20, "core": 5}

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[features.get_task_service] = lambda: task_service
        app.dependency_overrides[get_literature_service] = lambda: literature_service
        app.include_router(features.router)
        client = TestClient(app)

        response = client.post(
            "/workspaces/ws-1/features/thesis_writing/execute",
            json={"params": {"action": "write_chapter", "chapter_index": 0}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-789"
        assert data["warning"] is None

    def test_thesis_writing_no_check_for_other_actions(self):
        """Actions other than write_chapter/write_all should not check literature."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-789")

        literature_service = AsyncMock()
        literature_service.count_literature.return_value = {"total": 2, "core": 0}

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[features.get_task_service] = lambda: task_service
        app.dependency_overrides[get_literature_service] = lambda: literature_service
        app.include_router(features.router)
        client = TestClient(app)

        response = client.post(
            "/workspaces/ws-1/features/thesis_writing/execute",
            json={"params": {"action": "generate_outline"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-789"
        assert data["warning"] is None
        # literature_service should not be called
        literature_service.count_literature.assert_not_called()
