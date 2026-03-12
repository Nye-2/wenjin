"""Tests for features router."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import WorkspaceType
from src.gateway.routers import features
from src.gateway.routers.auth import get_current_user


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
) -> TestClient:
    """Create a features test client with dependency overrides."""
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_task_service():
        yield task_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[features.get_workspace_service] = (
        override_get_workspace_service
    )
    app.dependency_overrides[features.get_task_service] = override_get_task_service
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
