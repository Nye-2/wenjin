"""Execution commit router — POST /api/executions/{id}/commit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.services.change_set_review_service import (
    ChangeSetReviewNotFoundError,
    ChangeSetReviewPersistenceError,
    ChangeSetReviewService,
)
from src.services.execution_commit_service import (
    ExecutionCommitConcurrencyError,
    ExecutionCommitNotFoundError,
    ExecutionCommitPersistenceError,
    ExecutionCommitService,
)
from src.services.execution_service import ExecutionService

router = APIRouter(prefix="/api/executions", tags=["executions"])
_MAX_REQUEST_IDS = 200
_MAX_REQUEST_ID_LENGTH = 160


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class CommitRequest(BaseModel):
    accept_all: bool = False
    accepted_ids: list[str] | None = Field(default=None, max_length=_MAX_REQUEST_IDS)
    accepted_unit_ids: list[str] | None = Field(default=None, max_length=_MAX_REQUEST_IDS)

    @field_validator("accepted_ids", mode="before")
    @classmethod
    def _validate_accepted_ids(cls, value: Any) -> Any:
        return _validate_request_ids(value, field_name="accepted_ids")

    @field_validator("accepted_unit_ids", mode="before")
    @classmethod
    def _validate_accepted_unit_ids(cls, value: Any) -> Any:
        return _validate_request_ids(value, field_name="accepted_unit_ids")


class ChangeSetUnitsRequest(BaseModel):
    unit_ids: list[str] = Field(max_length=_MAX_REQUEST_IDS)

    @field_validator("unit_ids", mode="before")
    @classmethod
    def _validate_unit_ids(cls, value: Any) -> Any:
        return _validate_request_ids(value, field_name="unit_ids")


def _validate_request_ids(value: Any, *, field_name: str) -> Any:
    if value is None:
        return None
    if not isinstance(value, list):
        return value
    if len(value) > _MAX_REQUEST_IDS:
        raise ValueError(f"{field_name} must contain at most {_MAX_REQUEST_IDS} ids")
    for item in value:
        text = str(item or "").strip()
        if not text:
            raise ValueError(f"{field_name} must not contain blank ids")
        if len(text) > _MAX_REQUEST_ID_LENGTH:
            raise ValueError(
                f"{field_name} contains an id longer than {_MAX_REQUEST_ID_LENGTH} chars"
            )
    return value


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


def _get_change_set_review_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ChangeSetReviewService:
    return ChangeSetReviewService(
        execution_service=ExecutionService(dataservice=dataservice),
        dataservice=dataservice,
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
    - ``accepted_unit_ids`` selects specific accepted ChangeUnit IDs to write.
    - ``accepted_ids`` selects historical output IDs when no ChangeSet exists.
    - Run History is always recorded regardless of selection.
    - Idempotent when ``Idempotency-Key`` header is supplied (24h cache).
    """
    try:
        return await commit_service.commit_outputs(
            execution_id,
            accept_all=body.accept_all,
            accepted_ids=body.accepted_ids,
            accepted_unit_ids=body.accepted_unit_ids,
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


@router.get("/{execution_id}/changeset")
async def get_execution_change_set(
    execution_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    review_service: ChangeSetReviewService = Depends(_get_change_set_review_service),
) -> dict[str, Any]:
    """Return the execution ChangeSet plus the user's explicit review state."""
    try:
        return await review_service.get_change_set(
            execution_id,
            actor_user_id=str(current_user.id),
        )
    except ChangeSetReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ChangeSet not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_id}/changeset/accept")
async def accept_execution_change_set_units(
    execution_id: str,
    body: ChangeSetUnitsRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    review_service: ChangeSetReviewService = Depends(_get_change_set_review_service),
) -> dict[str, Any]:
    """Mark selected ChangeSet units as explicitly accepted."""
    try:
        return await review_service.accept_units(
            execution_id,
            unit_ids=body.unit_ids,
            actor_user_id=str(current_user.id),
        )
    except ChangeSetReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ChangeSet not found") from exc
    except ChangeSetReviewPersistenceError as exc:
        raise HTTPException(status_code=500, detail="ChangeSet review state persistence failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_id}/changeset/reject")
async def reject_execution_change_set_units(
    execution_id: str,
    body: ChangeSetUnitsRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    review_service: ChangeSetReviewService = Depends(_get_change_set_review_service),
) -> dict[str, Any]:
    """Mark selected ChangeSet units as rejected."""
    try:
        return await review_service.reject_units(
            execution_id,
            unit_ids=body.unit_ids,
            actor_user_id=str(current_user.id),
        )
    except ChangeSetReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ChangeSet not found") from exc
    except ChangeSetReviewPersistenceError as exc:
        raise HTTPException(status_code=500, detail="ChangeSet review state persistence failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_id}/changeset/undo")
async def undo_execution_change_set_units(
    execution_id: str,
    body: ChangeSetUnitsRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    review_service: ChangeSetReviewService = Depends(_get_change_set_review_service),
) -> dict[str, Any]:
    """Mark selected ChangeSet units as undone."""
    try:
        return await review_service.undo_units(
            execution_id,
            unit_ids=body.unit_ids,
            actor_user_id=str(current_user.id),
        )
    except ChangeSetReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ChangeSet not found") from exc
    except ChangeSetReviewPersistenceError as exc:
        raise HTTPException(status_code=500, detail="ChangeSet review state persistence failed") from exc
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
