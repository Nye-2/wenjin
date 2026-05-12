"""Workspace metadata helpers (workspace type lookup).

Historically this module exposed a ``skill name`` resolver layer over the
legacy :mod:`src.workspace_features.skills` registry.  That registry is gone —
capabilities and skills now live in the DB (see ``capabilities`` and
``capability_skills`` tables).  Only the workspace-type lookup helpers
survive, since they read directly from the ``workspaces`` table.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Workspace


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

    result = await db.execute(
        select(Workspace.id, Workspace.type).where(Workspace.id.in_(normalized_ids))
    )
    rows = result.all()
    if inspect.isawaitable(rows):
        rows = await rows
    try:
        normalized_rows = list(rows)
    except TypeError:
        return {}
    return {
        str(workspace_id): normalized_type
        for workspace_id, workspace_type in normalized_rows
        if (normalized_type := normalize_workspace_type(workspace_type)) is not None
    }


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
