"""Actor context propagated into DataService commands."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class ActorKind(enum.StrEnum):
    """Type of caller executing a DataService command."""

    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"
    WORKER = "worker"
    MIGRATION = "migration"


class ActorContext(BaseModel):
    """Canonical caller identity for DataService write operations."""

    actor_kind: ActorKind = ActorKind.SYSTEM
    actor_user_id: str | None = None
    workspace_id: str | None = None
    trace_id: str | None = None
    source_service: str = Field(default="unknown", min_length=1, max_length=80)

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> ActorContext:
        """Build an actor context from normalized request headers."""
        return cls(
            actor_kind=ActorKind(headers.get("x-wenjin-actor-kind", ActorKind.SYSTEM.value)),
            actor_user_id=headers.get("x-wenjin-actor-user-id") or None,
            workspace_id=headers.get("x-wenjin-workspace-id") or None,
            trace_id=headers.get("x-request-id") or headers.get("x-correlation-id") or None,
            source_service=headers.get("x-wenjin-source-service") or "unknown",
        )
