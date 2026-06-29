"""Execution commit router — POST /api/executions/{id}/commit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.services.execution_commit_service import (
    ExecutionCommitConcurrencyError,
    ExecutionCommitNotFoundError,
    ExecutionCommitPersistenceError,
    ExecutionCommitService,
)
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
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ExecutionCommitService:
    """Construct ExecutionCommitService against the canonical DataService."""
    try:
        from src.academic.cache.redis_client import redis_client as _rc
        _redis = _rc.client
    except Exception:
        _redis = None

    return ExecutionCommitService(
        execution_service=ExecutionService(dataservice=dataservice),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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
            actor_user_id=str(current_user.id),
        )
    except ExecutionCommitNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Execution not found") from exc
    except ExecutionCommitConcurrencyError as exc:
        raise HTTPException(status_code=409, detail="Commit already in progress") from exc
    except ExecutionCommitPersistenceError as exc:
        raise HTTPException(status_code=500, detail="Commit state persistence failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_id}/commit/undo")
async def undo_execution_commit(
    execution_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    commit_service: ExecutionCommitService = Depends(_get_commit_service),
) -> dict[str, Any]:
    """Undo the committed room writeback batch for an execution."""
    try:
        return await commit_service.undo_commit(
            execution_id,
            actor_user_id=str(current_user.id),
        )
    except ExecutionCommitNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Execution not found") from exc
    except ExecutionCommitPersistenceError as exc:
        raise HTTPException(status_code=500, detail="Commit state persistence failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
