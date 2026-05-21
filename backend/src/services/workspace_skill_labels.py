"""Workspace metadata helpers backed by DataService workspace projections."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.workspace_api import WorkspaceDataService


def normalize_workspace_type(workspace_type: Any) -> str | None:
    """Normalize enum-like workspace type values into plain strings."""
    if workspace_type is None:
        return None
    raw_value = getattr(workspace_type, "value", workspace_type)
    normalized = str(raw_value).strip()
    return normalized or None


def resolve_thread_workspace_type(thread: Any) -> str | None:
    """Best-effort workspace type lookup for thread-like objects."""
    explicit_workspace_type = normalize_workspace_type(
        getattr(thread, "workspace_type", None)
    )
    if explicit_workspace_type:
        return explicit_workspace_type
    workspace = getattr(thread, "workspace", None)
    return normalize_workspace_type(getattr(workspace, "type", None))


async def list_workspace_types(
    db: AsyncSession,
    workspace_ids: Iterable[str | None],
) -> dict[str, str]:
    """Resolve workspace types for a batch of workspace IDs."""
    normalized_ids = sorted(
        {
            str(workspace_id).strip()
            for workspace_id in workspace_ids
            if workspace_id is not None and str(workspace_id).strip()
        }
    )
    if not normalized_ids:
        return {}

    service = WorkspaceDataService(db, autocommit=False)
    resolved: dict[str, str] = {}
    for workspace_id in normalized_ids:
        workspace = await service.get_workspace(workspace_id)
        if workspace is None:
            continue
        normalized_type = normalize_workspace_type(getattr(workspace, "type", None))
        if normalized_type is not None:
            resolved[workspace_id] = normalized_type
    return resolved


async def get_workspace_type(
    db: AsyncSession,
    workspace_id: str | None,
) -> str | None:
    """Resolve a single workspace type from storage."""
    normalized_workspace_id = (workspace_id or "").strip()
    if not normalized_workspace_id:
        return None
    return (await list_workspace_types(db, [normalized_workspace_id])).get(
        normalized_workspace_id
    )
