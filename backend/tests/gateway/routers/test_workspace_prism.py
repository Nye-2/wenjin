"""Tests for workspace Prism routing endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.dataservice_client.contracts.prism import PrismFileVersionPayload
from src.gateway.routers import workspaces
from src.gateway.routers.auth import get_current_user


def _create_user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _create_workspace(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(
        id="ws-1",
        user_id=user_id,
        name="Workspace 1",
        type=SimpleNamespace(value="thesis"),
    )


def _payload(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        **data,
        model_dump=lambda mode="json": data,
    )


def _create_client(
    *,
    user_id: str,
    workspace_owner_id: str,
    dataservice: object | None = None,
) -> TestClient:
    app = FastAPI()

    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_create_workspace(workspace_owner_id))
    workspace_service.has_active_membership = AsyncMock(return_value=user_id == workspace_owner_id)

    async def override_get_current_user():
        return _create_user(user_id)

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_dataservice_client():
        return dataservice or AsyncMock()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_dataservice_client] = override_get_dataservice_client
    app.include_router(workspaces.router)
    return TestClient(app)


def test_prism_ensure_returns_workspace_prism_route():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspacePrismService.ensure_surface_projection",
        new=AsyncMock(
            return_value={
                "workspace_id": "ws-1",
                "prism_project_id": "prism-1",
                "latex_project_id": "latex-1",
                "surface_role": "primary_manuscript",
                "url": "/workspaces/ws-1/prism",
            }
        ),
    ) as ensure_surface:
        response = client.post("/workspaces/ws-1/prism/ensure")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "latex_project_id": "latex-1",
        "prism_project_id": "prism-1",
        "url": "/workspaces/ws-1/prism",
        "sync_status": "ready",
    }
    ensure_surface.assert_awaited_once()


def test_workspace_prism_surface_returns_linked_project_metadata():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspacePrismService.get_surface_projection",
        new=AsyncMock(
            return_value={
                "workspace_id": "ws-1",
                "latex_project_id": "latex-1",
                "surface_role": "primary_manuscript",
                "url": "/workspaces/ws-1/prism",
            }
        ),
    ):
        response = client.get("/workspaces/ws-1/prism")

    assert response.status_code == 200
    assert response.json()["latex_project_id"] == "latex-1"
    assert response.json()["url"] == "/workspaces/ws-1/prism"


def test_workspace_prism_surface_returns_404_when_project_missing():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspacePrismService.get_surface_projection",
        new=AsyncMock(side_effect=ValueError("missing")),
    ):
        response = client.get("/workspaces/ws-1/prism")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace Prism surface not found"


def test_workspace_prism_surface_rejects_non_owner():
    client = _create_client(user_id="user-2", workspace_owner_id="owner-1")
    response = client.get("/workspaces/ws-1/prism")
    assert response.status_code == 403


def test_prism_ensure_rejects_non_owner():
    client = _create_client(user_id="user-2", workspace_owner_id="owner-1")
    response = client.post("/workspaces/ws-1/prism/ensure")
    assert response.status_code == 403


def test_workspace_prism_file_read_returns_current_version():
    dataservice = AsyncMock()
    dataservice.get_prism_workspace_file = AsyncMock(
        return_value=_payload(
            {
                "file": {
                    "id": "file-1",
                    "workspace_id": "ws-1",
                    "document_id": "doc-1",
                    "path": "docs/spec.md",
                    "file_role": "manual",
                    "mime_type": "text/markdown",
                    "current_version_id": "version-1",
                    "content_hash": "sha256:old",
                    "sort_order": 0,
                    "metadata_json": {},
                    "deleted_at": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "current_version": {
                    "id": "version-1",
                    "workspace_id": "ws-1",
                    "file_id": "file-1",
                    "version_no": 1,
                    "mission_review_item_id": "review-1",
                    "mission_commit_id": "commit-1",
                    "content_inline": "# Spec",
                    "content_asset_id": None,
                    "content_hash": "sha256:old",
                    "created_by": "user-1",
                    "created_at": None,
                    "updated_at": None,
                },
            }
        )
    )
    client = _create_client(
        user_id="user-1",
        workspace_owner_id="user-1",
        dataservice=dataservice,
    )

    response = client.get(
        "/workspaces/ws-1/prism/files/file-1?prism_project_id=prism-1"
    )

    assert response.status_code == 200
    assert response.json()["current_version"]["content_inline"] == "# Spec"
    assert response.json()["current_version"]["mission_review_item_id"] == "review-1"
    assert response.json()["current_version"]["mission_commit_id"] == "commit-1"
    assert "review_item_id" not in response.json()["current_version"]
    dataservice.get_prism_workspace_file.assert_awaited_once_with(
        "ws-1",
        "file-1",
        prism_project_id="prism-1",
    )


def test_prism_revision_contract_rejects_legacy_review_item_id() -> None:
    with pytest.raises(ValidationError, match="review_item_id"):
        PrismFileVersionPayload.model_validate(
            {
                "id": "version-1",
                "workspace_id": "ws-1",
                "file_id": "file-1",
                "version_no": 1,
                "review_item_id": "legacy-review-1",
                "content_inline": "# Legacy",
                "content_hash": "sha256:legacy",
                "created_by": "user-1",
            }
        )


def test_workspace_prism_file_save_uses_expected_hash_and_backend_hash():
    dataservice = AsyncMock()
    dataservice.update_prism_workspace_file = AsyncMock(
        return_value=_payload(
            {
                "file": {
                    "id": "file-1",
                    "workspace_id": "ws-1",
                    "document_id": "doc-1",
                    "path": "docs/spec.md",
                    "file_role": "manual",
                    "mime_type": "text/markdown",
                    "current_version_id": "version-2",
                    "content_hash": "sha256:09b938bf2d8d508d7c22a4d23d9a19c6667d090aab7b50cdde7a41860c1f3b7b",
                    "sort_order": 0,
                    "metadata_json": {},
                    "deleted_at": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "version": {
                    "id": "version-2",
                    "workspace_id": "ws-1",
                    "file_id": "file-1",
                    "version_no": 2,
                    "mission_review_item_id": None,
                    "mission_commit_id": None,
                    "content_inline": "# Updated",
                    "content_asset_id": None,
                    "content_hash": "sha256:09b938bf2d8d508d7c22a4d23d9a19c6667d090aab7b50cdde7a41860c1f3b7b",
                    "created_by": "user-1",
                    "created_at": None,
                    "updated_at": None,
                },
                "changed": True,
                "skipped_reason": None,
            }
        )
    )
    client = _create_client(
        user_id="user-1",
        workspace_owner_id="user-1",
        dataservice=dataservice,
    )

    response = client.put(
        "/workspaces/ws-1/prism/files/file-1",
        json={"content_inline": "# Updated", "expected_current_hash": "sha256:old"},
    )

    assert response.status_code == 200
    command = dataservice.update_prism_workspace_file.await_args.args[2]
    assert command.content_inline == "# Updated"
    assert command.expected_current_hash == "sha256:old"
    assert command.content_hash.startswith("sha256:")


def test_workspace_prism_file_save_reports_hash_conflict():
    dataservice = AsyncMock()
    dataservice.update_prism_workspace_file = AsyncMock(
        return_value=_payload(
            {
                "file": {
                    "id": "file-1",
                    "workspace_id": "ws-1",
                    "document_id": "doc-1",
                    "path": "docs/spec.md",
                    "file_role": "manual",
                    "mime_type": "text/markdown",
                    "current_version_id": "version-1",
                    "content_hash": "sha256:newer",
                    "sort_order": 0,
                    "metadata_json": {},
                    "deleted_at": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "version": None,
                "changed": False,
                "skipped_reason": "hash_mismatch",
            }
        )
    )
    client = _create_client(
        user_id="user-1",
        workspace_owner_id="user-1",
        dataservice=dataservice,
    )

    response = client.put(
        "/workspaces/ws-1/prism/files/file-1",
        json={"content_inline": "# Updated", "expected_current_hash": "sha256:old"},
    )

    assert response.status_code == 409
