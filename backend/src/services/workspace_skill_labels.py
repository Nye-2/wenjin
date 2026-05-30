"""Workspace metadata helpers backed by DataService workspace projections."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


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
    workspace_ids: Iterable[str | None],
    *,
    dataservice: AsyncDataServiceClient | None = None,
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

    resolved: dict[str, str] = {}
    if dataservice is not None:
        for workspace_id in normalized_ids:
            workspace = await dataservice.get_workspace(workspace_id)
            if workspace is None:
                continue
            normalized_type = normalize_workspace_type(getattr(workspace, "type", None))
            if normalized_type is not None:
                resolved[workspace_id] = normalized_type
        return resolved
    async with dataservice_client() as client:
        return await list_workspace_types(normalized_ids, dataservice=client)
    return resolved


async def get_workspace_type(
    workspace_id: str | None,
    *,
    dataservice: AsyncDataServiceClient | None = None,
) -> str | None:
    """Resolve a single workspace type from storage."""
    normalized_workspace_id = (workspace_id or "").strip()
    if not normalized_workspace_id:
        return None
    return (await list_workspace_types(
        [normalized_workspace_id],
        dataservice=dataservice,
    )).get(
        normalized_workspace_id
    )
