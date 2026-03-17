"""P0-2 Smoke tests: one end-to-end path per workspace type.

Requirement (from docs/2026-03-16-phase3-review-and-next-actions.md §6.2):
  Each of the five canonical workspace types must have at least one smoke test
  covering 输入 → 执行 → 产出 → dashboard 状态刷新:
    1. Feature discovery lists expected features.
    2. Feature execution accepts valid params and returns pending task.
    3. Task payload carries correct canonical routing metadata.
    4. Response shape matches ExecuteResponse contract.

Workspace types and representative features:
  - thesis         → deep_research
  - sci            → literature_search
  - proposal       → proposal_outline
  - software_copyright → copyright_materials
  - patent         → patent_outline
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.handlers.feature_execution_handler import (
    get_credit_service,
    get_literature_service,
)
from src.database import WorkspaceType
from src.gateway.routers import features
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.tasks import get_task_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(user_id: str = "smoke-user") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _mock_workspace(
    ws_type: WorkspaceType,
    *,
    ws_id: str = "ws-smoke",
    user_id: str = "smoke-user",
    name: str = "Smoke Workspace",
    description: str = "Smoke-test workspace",
    discipline: str = "computer_science",
) -> MagicMock:
    ws = MagicMock()
    ws.id = ws_id
    ws.user_id = user_id
    ws.name = name
    ws.type = ws_type
    ws.description = description
    ws.discipline = discipline
    ws.config = {"template": "default"}
    return ws


def _mock_credit_service() -> AsyncMock:
    svc = AsyncMock()
    svc.consume_for_feature = AsyncMock(return_value=None)
    svc.refund_failed_task = AsyncMock(return_value=None)
    svc.db = AsyncMock()
    svc.db.commit = AsyncMock()
    return svc


def _make_client(
    ws_type: WorkspaceType,
    task_id: str = "task-smoke-1",
    literature_service=None,
) -> TestClient:
    """Build a TestClient wired for a specific workspace type."""
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace(ws_type))

    task_service = AsyncMock()
    task_service.submit_task = AsyncMock(return_value=task_id)
    task_service.find_active_task = AsyncMock(return_value=None)

    app = FastAPI()

    async def override_user():
        return _mock_user()

    async def override_ws():
        return workspace_service

    async def override_task():
        yield task_service

    async def override_lit():
        return literature_service or AsyncMock()

    async def override_credit():
        return _mock_credit_service()

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[features.get_workspace_service] = override_ws
    app.dependency_overrides[get_task_service] = override_task
    app.dependency_overrides[get_literature_service] = override_lit
    app.dependency_overrides[get_credit_service] = override_credit
    app.include_router(features.router)

    return TestClient(app), task_service


# ---------------------------------------------------------------------------
# Parametrised smoke matrix
# ---------------------------------------------------------------------------

# (workspace_type, feature_id, params, expected_handler_key, expected_task_type)
SMOKE_MATRIX = [
    pytest.param(
        WorkspaceType.THESIS,
        "deep_research",
        {"query": "深度学习在自然语言处理中的应用"},
        "thesis.deep_research",
        "deep_research",
        id="thesis-deep_research",
    ),
    pytest.param(
        WorkspaceType.SCI,
        "literature_search",
        {"query": "vision transformer attention mechanism"},
        "sci.literature_search",
        "workspace_feature",
        id="sci-literature_search",
    ),
    pytest.param(
        WorkspaceType.PROPOSAL,
        "proposal_outline",
        {"topic": "智能制造关键技术", "proposal_type": "provincial", "period_months": 36},
        "proposal.proposal_outline",
        "workspace_feature",
        id="proposal-proposal_outline",
    ),
    pytest.param(
        WorkspaceType.SOFTWARE_COPYRIGHT,
        "copyright_materials",
        {"software_name": "AcademiaGPT", "version": "V2.0"},
        "software_copyright.copyright_materials",
        "workspace_feature",
        id="software_copyright-copyright_materials",
    ),
    pytest.param(
        WorkspaceType.PATENT,
        "patent_outline",
        {
            "innovation_description": "基于Transformer的多模态学术文本生成方法",
            "technical_field": "人工智能",
        },
        "patent.patent_outline",
        "workspace_feature",
        id="patent-patent_outline",
    ),
]


class TestFiveWorkspaceSmoke:
    """P0-2: end-to-end smoke test for every canonical workspace type."""

    # ---- Step 1: Feature discovery ----

    @pytest.mark.parametrize(
        "ws_type, feature_id, _params, _hk, _tt",
        SMOKE_MATRIX,
    )
    def test_feature_discovery_includes_representative_feature(
        self, ws_type, feature_id, _params, _hk, _tt,
    ):
        """GET /workspaces/{id}/features returns the expected feature."""
        client, _ = _make_client(ws_type)
        resp = client.get("/workspaces/ws-smoke/features")
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()["features"]]
        assert feature_id in ids, (
            f"Expected '{feature_id}' in features for {ws_type.value}, got {ids}"
        )

    # ---- Step 2+3+4: Execute → payload → response ----

    @pytest.mark.parametrize(
        "ws_type, feature_id, params, expected_handler_key, expected_task_type",
        SMOKE_MATRIX,
    )
    def test_execute_returns_pending_task_with_correct_payload(
        self,
        ws_type,
        feature_id,
        params,
        expected_handler_key,
        expected_task_type,
    ):
        """POST execute returns a pending task and the canonical payload is correct."""
        task_id = f"task-{ws_type.value}-smoke"
        client, task_service = _make_client(ws_type, task_id=task_id)

        resp = client.post(
            f"/workspaces/ws-smoke/features/{feature_id}/execute",
            json={"params": params},
        )

        # -- Response contract --
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending"
        assert data["feature_id"] == feature_id
        assert data["warning"] is None

        # -- Submitted payload --
        submit_kwargs = task_service.submit_task.await_args.kwargs
        payload = submit_kwargs["payload"]

        # Canonical routing metadata
        assert payload["workspace_id"] == "ws-smoke"
        assert payload["workspace_type"] == ws_type.value
        assert payload["feature_id"] == feature_id
        assert payload["handler_key"] == expected_handler_key
        assert submit_kwargs["task_type"] == expected_task_type

        # User params are forwarded (flat-merged)
        for key, value in params.items():
            assert payload[key] == value, (
                f"param '{key}' not forwarded: expected {value!r}, got {payload.get(key)!r}"
            )

    # ---- Step 4b: Duplicate submission guard ----

    @pytest.mark.parametrize(
        "ws_type, feature_id, params, _hk, _tt",
        SMOKE_MATRIX,
    )
    def test_duplicate_execute_returns_existing_task(
        self, ws_type, feature_id, params, _hk, _tt,
    ):
        """When an active task already exists, no new task is submitted."""
        client, task_service = _make_client(ws_type, task_id="new-task-should-not-be-used")
        task_service.find_active_task = AsyncMock(return_value="existing-task-999")

        resp = client.post(
            f"/workspaces/ws-smoke/features/{feature_id}/execute",
            json={"params": params},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "existing-task-999"
        assert data["status"] == "pending"
        task_service.submit_task.assert_not_called()
