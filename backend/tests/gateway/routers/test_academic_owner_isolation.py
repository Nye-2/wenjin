"""Owner-isolation regression tests for legacy academic artifact routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.gateway.routers.academic import get_artifact_service, router
from src.gateway.routers.auth import get_current_user

WORKSPACE_ID = "550e8400-e29b-41d4-a716-446655440001"
OTHER_WORKSPACE_ID = "550e8400-e29b-41d4-a716-446655440099"
USER_ID = "550e8400-e29b-41d4-a716-446655440002"


def _make_artifact(artifact_id: str, workspace_id: str):
    artifact = MagicMock()
    artifact.id = artifact_id
    artifact.workspace_id = workspace_id
    artifact.type = "research_idea"
    artifact.title = "Title"
    artifact.content = {"k": "v"}
    artifact.created_by_skill = None
    artifact.parent_artifact_id = None
    artifact.version = 1
    artifact.status = "draft"
    artifact.created_at = datetime(2026, 1, 1, 0, 0, 0)
    artifact.updated_at = datetime(2026, 1, 1, 0, 0, 0)

    def _column(name: str):
        c = MagicMock()
        c.name = name
        return c

    artifact.__table__ = MagicMock()
    artifact.__table__.columns = [
        _column("id"),
        _column("workspace_id"),
        _column("type"),
        _column("title"),
        _column("content"),
        _column("created_by_skill"),
        _column("parent_artifact_id"),
        _column("version"),
        _column("status"),
        _column("created_at"),
        _column("updated_at"),
    ]
    return artifact


@pytest.fixture
def mock_artifact_service():
    service = AsyncMock()
    service.create = AsyncMock(
        return_value=_make_artifact("550e8400-e29b-41d4-a716-446655440010", WORKSPACE_ID)
    )
    service.list_by_workspace = AsyncMock(return_value=[])
    service.get = AsyncMock(
        return_value=_make_artifact("550e8400-e29b-41d4-a716-446655440011", WORKSPACE_ID)
    )
    service.get_lineage = AsyncMock(return_value=[])
    return service


@pytest.fixture
def client(mock_artifact_service):
    app = FastAPI()

    async def _current_user():
        user = MagicMock()
        user.id = USER_ID
        return user

    async def _artifact_service():
        return mock_artifact_service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_artifact_service] = _artifact_service
    app.include_router(router)
    return TestClient(app)


def test_list_artifacts_invokes_workspace_owner_check(
    client, mock_artifact_service, monkeypatch
):
    owner_session = object()
    require_owner = AsyncMock()
    monkeypatch.setattr(
        "src.gateway.routers.academic._owner_check_session_from_service",
        lambda service: owner_session,
    )
    monkeypatch.setattr(
        "src.gateway.routers.academic._require_workspace_owner",
        require_owner,
    )

    response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts")

    assert response.status_code == 200
    require_owner.assert_awaited_once_with(
        owner_session,
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
    )
    mock_artifact_service.list_by_workspace.assert_awaited_once_with(
        workspace_id=WORKSPACE_ID,
        type=None,
    )


def test_create_artifact_invokes_workspace_owner_check(
    client, mock_artifact_service, monkeypatch
):
    owner_session = object()
    require_owner = AsyncMock()
    monkeypatch.setattr(
        "src.gateway.routers.academic._owner_check_session_from_service",
        lambda service: owner_session,
    )
    monkeypatch.setattr(
        "src.gateway.routers.academic._require_workspace_owner",
        require_owner,
    )

    response = client.post(
        f"/workspaces/{WORKSPACE_ID}/artifacts",
        json={
            "type": "research_idea",
            "content": {"idea": "test"},
        },
    )

    assert response.status_code == 201
    require_owner.assert_awaited_once_with(
        owner_session,
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
    )
    mock_artifact_service.create.assert_awaited_once()


def test_list_artifacts_returns_403_when_owner_check_fails(client, monkeypatch):
    owner_session = object()

    async def _deny(*args, **kwargs):
        raise HTTPException(status_code=403, detail="Access denied")

    monkeypatch.setattr(
        "src.gateway.routers.academic._owner_check_session_from_service",
        lambda service: owner_session,
    )
    monkeypatch.setattr(
        "src.gateway.routers.academic._require_workspace_owner",
        _deny,
    )

    response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts")

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


def test_get_artifact_requires_workspace_match(client, mock_artifact_service, monkeypatch):
    owner_session = object()
    monkeypatch.setattr(
        "src.gateway.routers.academic._owner_check_session_from_service",
        lambda service: owner_session,
    )
    monkeypatch.setattr(
        "src.gateway.routers.academic._require_workspace_owner",
        AsyncMock(),
    )
    mock_artifact_service.get = AsyncMock(
        return_value=_make_artifact(
            "550e8400-e29b-41d4-a716-446655440012",
            OTHER_WORKSPACE_ID,
        )
    )

    response = client.get(
        f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440012"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


def test_lineage_requires_workspace_match(client, mock_artifact_service, monkeypatch):
    owner_session = object()
    monkeypatch.setattr(
        "src.gateway.routers.academic._owner_check_session_from_service",
        lambda service: owner_session,
    )
    monkeypatch.setattr(
        "src.gateway.routers.academic._require_workspace_owner",
        AsyncMock(),
    )
    mock_artifact_service.get = AsyncMock(
        return_value=_make_artifact(
            "550e8400-e29b-41d4-a716-446655440013",
            OTHER_WORKSPACE_ID,
        )
    )

    response = client.get(
        f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440013/lineage"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"
    mock_artifact_service.get_lineage.assert_not_awaited()
