"""Execution commit router — POST /api/executions/{id}/commit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps import get_db
from src.gateway.deps.core import get_dataservice_client
from src.services.execution_commit_service import ExecutionCommitService
from src.services.execution_service import ExecutionService

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

def _get_commit_service(
    db: AsyncSession = Depends(get_db),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ExecutionCommitService:
    """Construct ExecutionCommitService from per-request DB session."""
    try:
        from src.academic.cache.redis_client import redis_client as _rc
        _redis = _rc.client
    except Exception:
        _redis = None

    return ExecutionCommitService(
        execution_service=ExecutionService(db, dataservice=dataservice),
        dataservice=dataservice,
        redis=_redis,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/{execution_id}/commit")
async def commit_execution_outputs(
    execution_id: str,
    body: CommitRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
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
