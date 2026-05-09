"""Capabilities router — spec §4.5.6 / §5.3.

GET /capabilities?workspace_type=thesis
GET /capabilities/{capability_id}?workspace_type=thesis

The CapabilityResolver singleton is created lazily on first use and stored on
``app.state``.  For V1 we don't seed capabilities at startup — that is a
Phase 2 concern.  An empty list / 404 is returned when the DB has no rows.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.database import User
from src.gateway.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


# ---------------------------------------------------------------------------
# Resolver dependency
# ---------------------------------------------------------------------------


async def _get_resolver(request: Request) -> "CapabilityResolver":
    """Return the per-app CapabilityResolver singleton.

    Created lazily on first call and cached on ``app.state``.
    Uses a minimal no-op EventBus stub so the resolver can be instantiated
    without a live Redis connection in the gateway process.
    """
    from src.services.capability_resolver import CapabilityResolver

    if not hasattr(request.app.state, "capability_resolver"):
        from src.database import get_db_session

        class _NoOpEventBus:
            """Minimal EventBus stub — real bus wired in Phase 2."""

            def subscribe(self, channel: str, handler: Any) -> None:  # noqa: ANN401
                pass  # no-op

        resolver = CapabilityResolver(
            session_factory=get_db_session,
            event_bus=_NoOpEventBus(),  # type: ignore[arg-type]
        )
        request.app.state.capability_resolver = resolver

    return request.app.state.capability_resolver  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _capability_to_dict(cap: Any) -> dict[str, Any]:
    """Convert a Capability ORM row to a plain dict."""
    if hasattr(cap, "__dict__"):
        return {k: v for k, v in cap.__dict__.items() if not k.startswith("_")}
    return dict(cap)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_capabilities(
    workspace_type: str = Query(..., description="Workspace type, e.g. thesis"),
    current_user: User = Depends(get_current_user),
    resolver: "CapabilityResolver" = Depends(_get_resolver),
) -> dict[str, Any]:
    """List all active capabilities for the given workspace type."""
    from src.services.capability_resolver import CapabilityResolver  # noqa: F401

    caps = await resolver.list_for_workspace_type(workspace_type)
    return {"items": [_capability_to_dict(c) for c in caps], "count": len(caps)}


@router.get("/{capability_id}")
async def get_capability(
    capability_id: str,
    workspace_type: str = Query(..., description="Workspace type, e.g. thesis"),
    current_user: User = Depends(get_current_user),
    resolver: "CapabilityResolver" = Depends(_get_resolver),
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

    return _capability_to_dict(cap)
