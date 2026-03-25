"""Workspace catalog and artifact lookup helpers for feature bridge."""

from __future__ import annotations

from typing import Any

from src.academic.services import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.application.handlers.feature_execution_handler import resolve_workspace_type
from src.database import get_db_session


async def build_workspace_artifact_overview(
    workspace_id: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """List latest workspace artifacts for tool use."""
    async with get_db_session() as db:
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


async def build_workspace_feature_overview(workspace_id: str) -> dict[str, Any] | None:
    """Build a lightweight feature catalog for the current workspace."""
    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get(workspace_id)
        if workspace is None:
            return None

        from src.workspace_features import list_workspace_features

        workspace_type = resolve_workspace_type(workspace)
        return {
            "workspace_id": str(workspace.id),
            "workspace_type": workspace_type,
            "features": [
                feature.to_api_dict()
                for feature in list_workspace_features(workspace_type)
            ],
        }


async def load_latest_workspace_artifacts(
    workspace_id: str,
    *,
    limit: int = 6,
) -> list[Any]:
    """Load recent workspace artifacts for param resolution helpers."""
    async with get_db_session() as db:
        service = ArtifactService(db)
        return await service.list_by_workspace(
            workspace_id=workspace_id,
            limit=limit,
            offset=0,
        )


async def load_latest_draft_summary(workspace_id: str) -> tuple[str | None, str | None]:
    """Load the latest draft-ish artifact summary used to infer follow-up params."""
    artifacts = await load_latest_workspace_artifacts(workspace_id, limit=12)
    for artifact in artifacts:
        content = artifact.content if isinstance(artifact.content, dict) else {}
        if artifact.type in {"paper_draft", "framework_outline", "thesis_chapter"}:
            title = str(
                content.get("paper_title")
                or content.get("section_title")
                or artifact.title
                or ""
            ).strip() or None
            excerpt = str(
                content.get("summary")
                or content.get("abstract")
                or content.get("content")
                or content.get("markdown")
                or ""
            ).strip()
            return title, excerpt[:2000] or None
    return None, None
