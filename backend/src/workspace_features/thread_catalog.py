"""Workspace catalog and artifact lookup helpers for thread-facing tools."""

from __future__ import annotations

from typing import Any

from src.academic.services import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.application.workspace_resolvers import resolve_workspace_type
from src.database import get_db_session
from src.workspace_features.skills import (
    get_default_skill_for_feature,
    list_feature_skill_ids,
)


async def build_workspace_artifact_overview(
    workspace_id: str,
    *,
    user_id: str | None,
    limit: int = 8,
) -> list[dict[str, Any]] | None:
    """List latest workspace artifacts for tool use."""
    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get(workspace_id)
        if workspace is None:
            return None
        if user_id is not None and str(workspace.user_id) != str(user_id):
            return None

        service = ArtifactService(db)
        artifacts = await service.list_by_workspace(
            workspace_id=workspace_id,
            limit=limit,
            offset=0,
        )
        return [
            {
                "id": str(artifact.id),
                "type": artifact.type,
                "title": artifact.title,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            for artifact in artifacts
        ]


async def build_workspace_feature_overview(
    workspace_id: str,
    *,
    user_id: str | None,
) -> dict[str, Any] | None:
    """Build a lightweight feature catalog for the current workspace."""
    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get(workspace_id)
        if workspace is None:
            return None
        if user_id is not None and str(workspace.user_id) != str(user_id):
            return None

        from src.workspace_features import list_workspace_features

        workspace_type = resolve_workspace_type(workspace)
        return {
            "workspace_id": str(workspace.id),
            "workspace_type": workspace_type,
            "features": [
                feature.to_api_dict()
                | {
                    "defaultSkillId": get_default_skill_for_feature(workspace_type, feature.id),
                    "entrySkillIds": list(list_feature_skill_ids(workspace_type, feature.id)),
                }
                for feature in list_workspace_features(workspace_type)
            ],
        }
