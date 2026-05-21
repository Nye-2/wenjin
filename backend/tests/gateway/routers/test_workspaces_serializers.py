"""Workspace router serialization tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.database.models.workspace import WorkspaceType
from src.dataservice.domains.workspace.contracts import WorkspaceRecord
from src.gateway.routers.workspaces_serializers import workspace_to_response


def test_workspace_to_response_accepts_dataservice_workspace_record() -> None:
    created_at = datetime(2026, 5, 21, tzinfo=UTC)
    updated_at = datetime(2026, 5, 22, tzinfo=UTC)
    record = WorkspaceRecord(
        id="ws-1",
        created_by_user_id="user-1",
        name="Research Workspace",
        workspace_type=WorkspaceType.SCI,
        discipline="computer_science",
        description="Paper workbench",
        settings_json={"language": "zh"},
        created_at=created_at,
        updated_at=updated_at,
    )

    response = workspace_to_response(record)

    assert response.id == "ws-1"
    assert response.user_id == "user-1"
    assert response.type == "sci"
    assert response.config == {"language": "zh"}
    assert response.created_at == created_at.isoformat()
    assert response.updated_at == updated_at.isoformat()
