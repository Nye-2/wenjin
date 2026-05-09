"""Execution commit router — POST /api/executions/{id}/commit."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.gateway.deps import get_db
from src.services.event_bus import EventBus
from src.services.execution_commit_service import ExecutionCommitService
from src.services.execution_service import ExecutionService
from src.services.rooms.decisions_service import DecisionsService
from src.services.rooms.documents_service import DocumentsService
from src.services.rooms.library_service import LibraryService
from src.services.rooms.memory_service import MemoryService
from src.services.rooms.run_history_service import RunHistoryService
from src.services.rooms.workspace_tasks_service import WorkspaceTasksService

router = APIRouter(prefix="/api/executions", tags=["executions"])


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class CommitRequest(BaseModel):
    accept_all: bool = False
    accepted_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _get_commit_service(db: AsyncSession = Depends(get_db)) -> ExecutionCommitService:
    """Construct ExecutionCommitService from per-request DB session."""
    # EventBus requires a Redis client. For requests we use a lightweight
    # stub so the service can still publish (fails silently if Redis unavailable).
    try:
        from src.academic.cache.redis_client import redis_client as _rc
        _redis = _rc.client
    except Exception:
        _redis = None

    bus: EventBus
    if _redis is not None:
        bus = EventBus(_redis)
    else:
        # No-op bus — publish will never be called
        bus = _NoopBus()  # type: ignore[assignment]

    return ExecutionCommitService(
        execution_service=ExecutionService(db),
        library_service=LibraryService(db),
        documents_service=DocumentsService(db),
        decisions_service=DecisionsService(db),
        memory_service=MemoryService(db),
        workspace_tasks_service=WorkspaceTasksService(db),
        run_history_service=RunHistoryService(db),
        event_bus=bus,
        redis=_redis,
    )


class _NoopBus:
    """Minimal stand-in used when Redis is unavailable at request time."""

    async def publish(self, channel: str, event: dict) -> int:  # noqa: D401
        return 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/{execution_id}/commit")
async def commit_execution_outputs(
    execution_id: str,
    body: CommitRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    commit_service: ExecutionCommitService = Depends(_get_commit_service),
) -> dict[str, Any]:
    """Commit selected execution outputs to rooms.

    - ``accept_all=true`` writes all outputs.
    - ``accepted_ids`` selects specific output IDs to write.
    - Run History is always recorded regardless of selection.
    - Idempotent when ``Idempotency-Key`` header is supplied (24h cache).
    """
    try:
        return await commit_service.commit_outputs(
            execution_id,
            accept_all=body.accept_all,
            accepted_ids=body.accepted_ids,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
