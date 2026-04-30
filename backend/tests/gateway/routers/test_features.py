"""Tests for features router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.results import FeatureTaskSubmission
from src.database import WorkspaceType
from src.gateway.deps import get_credit_service, get_reference_service
from src.gateway.deps.core import get_db
from src.gateway.routers import features
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.features import ExecuteResponse
from src.gateway.routers.tasks import get_task_service


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


def create_mock_credit_service() -> AsyncMock:
    """Create a credit service mock that skips real DB interactions."""
    credit_service = AsyncMock()
    credit_service.consume_for_feature = AsyncMock(return_value=None)
    credit_service.refund_failed_task = AsyncMock(return_value=None)
    credit_service.db = AsyncMock()
    credit_service.db.commit = AsyncMock()
    return credit_service


def create_client(
    user_id: str,
    workspace_service,
    task_service,
    reference_service=None,
    credit_service=None,
) -> TestClient:
    """Create a features test client with dependency overrides."""
    # Default find_active_task to None only if not explicitly configured by the test.
    # When AsyncMock auto-creates an attribute, its return_value is itself another
    # AsyncMock.  If the test explicitly set it (e.g. return_value="task-123"),
    # the return_value will be a str/None, so we skip the override.
    fat_rv = task_service.find_active_task.return_value
    if isinstance(fat_rv, AsyncMock):
        task_service.find_active_task = AsyncMock(return_value=None)
    app = FastAPI()

    async def override_get_current_user():
        return create_mock_user(user_id)

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_task_service():
        yield task_service

    async def override_get_reference_service():
        return reference_service or AsyncMock()

    async def override_get_credit_service():
        return credit_service or create_mock_credit_service()

    async def override_get_db():
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        yield db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[features.get_workspace_service] = (
        override_get_workspace_service
    )
    app.dependency_overrides[get_task_service] = override_get_task_service
    app.dependency_overrides[get_reference_service] = override_get_reference_service
    app.dependency_overrides[get_credit_service] = override_get_credit_service
    app.dependency_overrides[get_db] = override_get_db
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
        ]
        assert data["features"][0]["defaultSkillId"] == "deep-research"
        assert data["features"][3]["defaultSkillId"] == "framework-designer"

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
        payload = response.json()
        assert payload["task_id"] == "task-123"
        assert payload["execution_session_id"]
        assert payload["status"] == "pending"
        assert payload["feature_id"] == "copyright_materials"
        assert payload["message"] == "Queued 材料准备"
        assert payload["warning"] is None
        assert payload["detail"] is None

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
            "execution_session_id": payload["execution_session_id"],
            "skill_id": "copyright-writer",
            "skill_name": "著作权材料",
            "params": {"project_name": "Alpha"},
        }

    @pytest.mark.asyncio
    async def test_execute_feature_passes_redis_without_idempotency_key(self):
        """Workspace lock should still be available even when Idempotency-Key is absent."""
        request = features.ExecuteRequest(params={"k": "v"}, thread_id="thread-1")

        mock_launch_service = AsyncMock()
        mock_launch_service.launch = AsyncMock(
            return_value=MagicMock(
                execution_session_id="exec-1",
                outcome=FeatureTaskSubmission(
                    task_id="task-123",
                    feature_id="deep_research",
                    message="Queued Deep Research",
                ),
            )
        )

        from src.academic.cache.redis_client import redis_client as global_redis_client
        original_client = global_redis_client._client
        global_redis_client._client = object()
        try:
            with patch("src.config.redis_settings") as mock_redis_settings:
                mock_redis_settings.enabled = True
                response = await features.execute_feature(
                    workspace_id="ws-1",
                    feature_id="deep_research",
                    request=request,
                    launch_service=mock_launch_service,
                    idempotency_key=None,
                )
        finally:
            global_redis_client._client = original_client

        command = mock_launch_service.launch.await_args.args[0]
        assert command.redis_client is global_redis_client
        assert isinstance(response, ExecuteResponse)

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

    def test_execute_technical_description_submits_canonical_task_payload(self):
        """Technical description feature should be routed with canonical metadata."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SOFTWARE_COPYRIGHT)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-tech-1")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/technical_description/execute",
            json={
                "params": {
                    "software_name": "Academic Assistant",
                    "version": "V2.2",
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-tech-1"
        assert data["feature_id"] == "technical_description"
        assert data["status"] == "pending"

        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"]["workspace_type"] == "software_copyright"
        assert submit_kwargs["payload"]["feature_id"] == "technical_description"
        assert submit_kwargs["payload"]["handler_key"] == (
            "software_copyright.technical_description"
        )
        assert submit_kwargs["payload"]["params"] == {
            "software_name": "Academic Assistant",
            "version": "V2.2",
        }
        assert "software_name" not in submit_kwargs["payload"]
        assert "version" not in submit_kwargs["payload"]

    def test_execute_prior_art_search_submits_canonical_task_payload(self):
        """Patent prior_art_search feature should be routed with canonical metadata."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.PATENT)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-pat-1")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/prior_art_search/execute",
            json={
                "params": {
                    "keywords": ["调度优化", "强化学习"],
                    "time_range": "近3年",
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-pat-1"
        assert data["feature_id"] == "prior_art_search"
        assert data["status"] == "pending"

        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"]["workspace_type"] == "patent"
        assert submit_kwargs["payload"]["feature_id"] == "prior_art_search"
        assert submit_kwargs["payload"]["handler_key"] == "patent.prior_art_search"
        assert submit_kwargs["payload"]["params"] == {
            "keywords": ["调度优化", "强化学习"],
            "time_range": "近3年",
        }
        assert "keywords" not in submit_kwargs["payload"]
        assert "time_range" not in submit_kwargs["payload"]

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
        assert submit_kwargs["payload"]["params"]["software_name"] == "SafeName"
        assert "software_name" not in submit_kwargs["payload"]

    def test_execute_sci_literature_search_submits_expected_payload(self):
        """SCI literature search should route through canonical sci handler key."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SCI)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-sci-1")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/literature_search/execute",
            json={"params": {"query": "vision transformer"}},
        )

        assert response.status_code == 200
        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"]["workspace_type"] == "sci"
        assert submit_kwargs["payload"]["feature_id"] == "literature_search"
        assert submit_kwargs["payload"]["handler_key"] == "sci.literature_search"
        assert submit_kwargs["payload"]["params"] == {"query": "vision transformer"}
        assert "query" not in submit_kwargs["payload"]

    def test_execute_sci_writing_submits_expected_payload(self):
        """SCI writing should route through canonical sci writing handler key."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.SCI)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-sci-writing-1")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/writing/execute",
            json={
                "params": {
                    "paper_title": "Diffusion Models in Vision",
                    "section_type": "introduction",
                    "target_words": 1200,
                }
            },
        )

        assert response.status_code == 200
        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"]["workspace_type"] == "sci"
        assert submit_kwargs["payload"]["feature_id"] == "writing"
        assert submit_kwargs["payload"]["handler_key"] == "sci.writing"
        assert submit_kwargs["payload"]["params"] == {
            "paper_title": "Diffusion Models in Vision",
            "section_type": "introduction",
            "target_words": 1200,
        }
        assert "paper_title" not in submit_kwargs["payload"]
        assert "section_type" not in submit_kwargs["payload"]
        assert "target_words" not in submit_kwargs["payload"]

    def test_execute_proposal_outline_submits_expected_payload(self):
        """Proposal outline should route through canonical proposal handler key."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.PROPOSAL)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-proposal-1")
        client = create_client("user-1", workspace_service, task_service)

        response = client.post(
            "/workspaces/ws-1/features/proposal_outline/execute",
            json={
                "params": {
                    "topic": "智能制造关键技术研究",
                    "proposal_type": "provincial",
                    "period_months": 24,
                }
            },
        )

        assert response.status_code == 200
        submit_kwargs = task_service.submit_task.await_args.kwargs
        assert submit_kwargs["task_type"] == "workspace_feature"
        assert submit_kwargs["payload"]["workspace_type"] == "proposal"
        assert submit_kwargs["payload"]["feature_id"] == "proposal_outline"
        assert submit_kwargs["payload"]["handler_key"] == "proposal.proposal_outline"
        assert submit_kwargs["payload"]["params"] == {
            "topic": "智能制造关键技术研究",
            "proposal_type": "provincial",
            "period_months": 24,
        }
        assert "topic" not in submit_kwargs["payload"]


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
        task_service.find_active_task = AsyncMock(return_value=None)

        reference_service = AsyncMock()
        reference_service.count_references.return_value = {"total": 2, "core": 0}
        credit_service = create_mock_credit_service()

        # Create client with reference_service override
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[get_task_service] = lambda: task_service
        app.dependency_overrides[get_reference_service] = lambda: reference_service
        app.dependency_overrides[get_credit_service] = lambda: credit_service
        app.dependency_overrides[get_db] = create_client(
            "user-1",
            workspace_service,
            task_service,
            reference_service=reference_service,
            credit_service=credit_service,
        ).app.dependency_overrides[get_db]
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
        task_service.find_active_task = AsyncMock(return_value=None)

        reference_service = AsyncMock()
        reference_service.count_references.return_value = {"total": 20, "core": 5}
        credit_service = create_mock_credit_service()

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[get_task_service] = lambda: task_service
        app.dependency_overrides[get_reference_service] = lambda: reference_service
        app.dependency_overrides[get_credit_service] = lambda: credit_service
        app.dependency_overrides[get_db] = create_client(
            "user-1",
            workspace_service,
            task_service,
            reference_service=reference_service,
            credit_service=credit_service,
        ).app.dependency_overrides[get_db]
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
        task_service.find_active_task = AsyncMock(return_value=None)

        reference_service = AsyncMock()
        reference_service.count_references.return_value = {"total": 2, "core": 0}
        credit_service = create_mock_credit_service()

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: create_mock_user("user-1")
        app.dependency_overrides[features.get_workspace_service] = lambda: workspace_service
        app.dependency_overrides[get_task_service] = lambda: task_service
        app.dependency_overrides[get_reference_service] = lambda: reference_service
        app.dependency_overrides[get_credit_service] = lambda: credit_service
        app.dependency_overrides[get_db] = create_client(
            "user-1",
            workspace_service,
            task_service,
            reference_service=reference_service,
            credit_service=credit_service,
        ).app.dependency_overrides[get_db]
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
        # reference_service should not be called
        reference_service.count_references.assert_not_called()


class TestIdempotentExecution:
    """Tests for idempotent execution – duplicate requests reuse existing tasks."""

    def test_duplicate_execute_returns_existing_task(self):
        """When a pending/running task already exists for (workspace, feature, action),
        the endpoint should return the existing task_id and skip billing."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="new-task-id")
        task_service.find_active_task = AsyncMock(return_value="existing-task-123")

        reference_service = AsyncMock()
        reference_service.count_references.return_value = {"total": 20, "core": 5}
        credit_service = create_mock_credit_service()

        client = create_client(
            "user-1",
            workspace_service,
            task_service,
            reference_service=reference_service,
            credit_service=credit_service,
        )

        response = client.post(
            "/workspaces/ws-1/features/thesis_writing/execute",
            json={"params": {"action": "generate_outline"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "existing-task-123"
        assert data["status"] == "pending"
        # No new task should have been submitted
        task_service.submit_task.assert_not_called()
        # No credit should have been consumed
        credit_service.consume_for_feature.assert_not_called()

    def test_no_active_task_proceeds_normally(self):
        """When no active task exists, normal execution flow proceeds."""
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.THESIS)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="new-task-id")
        task_service.find_active_task = AsyncMock(return_value=None)

        reference_service = AsyncMock()
        reference_service.count_references.return_value = {"total": 20, "core": 5}
        credit_service = create_mock_credit_service()

        client = create_client(
            "user-1",
            workspace_service,
            task_service,
            reference_service=reference_service,
            credit_service=credit_service,
        )

        response = client.post(
            "/workspaces/ws-1/features/thesis_writing/execute",
            json={"params": {"action": "generate_outline"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "new-task-id"
        task_service.submit_task.assert_called_once()


class TestCreditsGuard:
    """Feature launch no longer pre-charges fixed credits."""

    def test_execute_feature_does_not_precharge_fixed_credits(self):
        workspace_service = AsyncMock()
        workspace_service.get = AsyncMock(
            return_value=create_workspace(WorkspaceType.PATENT)
        )
        task_service = AsyncMock()
        task_service.submit_task = AsyncMock(return_value="task-xyz")
        task_service.find_active_task = AsyncMock(return_value=None)

        credit_service = create_mock_credit_service()

        client = create_client(
            "user-1",
            workspace_service,
            task_service,
            credit_service=credit_service,
        )

        response = client.post(
            "/workspaces/ws-1/features/prior_art_search/execute",
            json={"params": {"query": "routing"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-xyz"
        assert data["status"] == "pending"
        credit_service.consume_for_feature.assert_not_called()
        task_service.submit_task.assert_called_once()
