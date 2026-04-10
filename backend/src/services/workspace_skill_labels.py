"""Workspace-aware skill label helpers for API and SSE contracts."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.lead_agent.chat_skill_catalog import (
    get_skill_by_id,
    list_feature_skill_ids,
    resolve_skill_for_feature,
)
from src.database import Workspace


def normalize_workspace_type(workspace_type: Any) -> str | None:
    """Normalize enum-like workspace type values into plain strings."""
    if workspace_type is None:
        return None
    raw_value = getattr(workspace_type, "value", workspace_type)
    normalized = str(raw_value).strip()
    return normalized or None


def resolve_workspace_skill_name(
    workspace_type: Any,
    skill_id: str | None,
) -> str | None:
    """Resolve a chat skill label from canonical workspace metadata."""
    normalized_skill_id = (skill_id or "").strip()
    if not normalized_skill_id:
        return None
    skill = get_skill_by_id(normalize_workspace_type(workspace_type), normalized_skill_id)
    return skill.name if skill is not None else None


def resolve_workspace_feature_skill_id(
    workspace_type: Any,
    feature_id: str | None,
    params: dict[str, Any] | None = None,
    *,
    preferred_skill_id: str | None = None,
) -> str | None:
    """Resolve the canonical chat skill ID for a feature execution."""
    skill = resolve_skill_for_feature(
        normalize_workspace_type(workspace_type),
        str(feature_id or "").strip(),
        params=params,
        preferred_skill_id=preferred_skill_id,
    )
    return skill.id if skill is not None else None


def resolve_workspace_feature_skill_name(
    workspace_type: Any,
    feature_id: str | None,
    params: dict[str, Any] | None = None,
    *,
    preferred_skill_id: str | None = None,
) -> str | None:
    """Resolve the canonical chat skill label for a feature execution."""
    skill = resolve_skill_for_feature(
        normalize_workspace_type(workspace_type),
        str(feature_id or "").strip(),
        params=params,
        preferred_skill_id=preferred_skill_id,
    )
    return skill.name if skill is not None else None


def list_workspace_feature_creator_ids(
    workspace_type: Any,
    feature_id: str | None,
) -> tuple[str, ...]:
    """Return canonical creator skill IDs for a feature's artifacts."""
    normalized_workspace_type = normalize_workspace_type(workspace_type)
    normalized_feature_id = str(feature_id or "").strip()
    if not normalized_workspace_type or not normalized_feature_id:
        return ()
    return list_feature_skill_ids(normalized_workspace_type, normalized_feature_id)


def resolve_thread_workspace_type(thread: Any) -> str | None:
    """Best-effort workspace type lookup for thread-like objects."""
    explicit_workspace_type = normalize_workspace_type(
        getattr(thread, "workspace_type", None)
    )
    if explicit_workspace_type:
        return explicit_workspace_type
    workspace = getattr(thread, "workspace", None)
    return normalize_workspace_type(getattr(workspace, "type", None))


def resolve_thread_skill_name(thread: Any) -> str | None:
    """Best-effort skill label lookup for thread-like objects."""
    explicit_skill_name = getattr(thread, "skill_name", None)
    if isinstance(explicit_skill_name, str) and explicit_skill_name.strip():
        return explicit_skill_name.strip()
    return resolve_workspace_skill_name(
        resolve_thread_workspace_type(thread),
        getattr(thread, "skill", None),
    )


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
