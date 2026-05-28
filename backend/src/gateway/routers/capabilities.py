"""Capabilities router — spec §4.5.6 / §5.3.

GET /capabilities?workspace_type=thesis
GET /capabilities/{capability_id}?workspace_type=thesis

The CapabilityResolver singleton is created lazily on first use and stored on
``app.state``.  For V1 we don't seed capabilities at startup — that is a
Phase 2 concern.  An empty list / 404 is returned when the DB has no rows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.database import User
from src.gateway.auth_dependencies import get_current_user

if TYPE_CHECKING:
    from src.services.capability_resolver import CapabilityResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


# ---------------------------------------------------------------------------
# Resolver dependency
# ---------------------------------------------------------------------------


async def _get_resolver(request: Request) -> CapabilityResolver:
    """Return the per-app CapabilityResolver singleton.

    Created lazily on first call and cached on ``app.state``.
    Wires the real Redis-backed EventBus for cache invalidation.
    """
    from src.services.capability_resolver import CapabilityResolver

    if not hasattr(request.app.state, "capability_resolver"):
        from src.academic.cache.redis_client import redis_client
        from src.database import get_db_session
        from src.services.event_bus import EventBus

        if redis_client._client is None:
            await redis_client.connect()

        resolver = CapabilityResolver(
            session_factory=get_db_session,
            event_bus=EventBus(redis_client.client),
        )
        request.app.state.capability_resolver = resolver

    return request.app.state.capability_resolver  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _capability_to_dict(cap: Any) -> dict[str, Any]:
    """Convert a Capability ORM row to a plain dict with explicit field mapping."""
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "tier": getattr(cap, "tier", "primary"),
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": cap.trigger_phrases,
        "required_decisions": cap.required_decisions,
        "brief_schema": cap.brief_schema,
        "graph_template": cap.graph_template,
        "ui_meta": cap.ui_meta,
        "runtime": cap.runtime,
        "dashboard_meta": cap.dashboard_meta,
        "notes": cap.notes,
    }


def _is_hidden_capability(cap: Any) -> bool:
    ui_meta = dict(getattr(cap, "ui_meta", None) or {})
    return getattr(cap, "tier", None) == "hidden" or ui_meta.get("entry_tier") == "hidden"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_capabilities(
    workspace_type: str = Query(..., description="Workspace type, e.g. thesis"),
    current_user: User = Depends(get_current_user),
    resolver: CapabilityResolver = Depends(_get_resolver),
) -> dict[str, Any]:
    """List all active capabilities for the given workspace type."""
    caps = await resolver.list_for_workspace_type(workspace_type)
    visible = [cap for cap in caps if not _is_hidden_capability(cap)]
    return {"items": [_capability_to_dict(c) for c in visible], "count": len(visible)}


@router.get("/{capability_id}")
async def get_capability(
    capability_id: str,
    workspace_type: str = Query(..., description="Workspace type, e.g. thesis"),
    current_user: User = Depends(get_current_user),
    resolver: CapabilityResolver = Depends(_get_resolver),
) -> dict[str, Any]:
    """Return full detail for a single capability."""
    from src.services.capability_resolver import CapabilityNotFound

    try:
        cap = await resolver.resolve(capability_id, workspace_type)
    except CapabilityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if _is_hidden_capability(cap):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{capability_id}' not found for workspace type '{workspace_type}'",
        )

    return _capability_to_dict(cap)
