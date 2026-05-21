"""Review batch endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.review.contracts import (
    ReviewBatchCreateCommand,
    ReviewItemDecisionCommand,
    ReviewItemTransitionCommand,
)
from src.dataservice.domains.review.service import DataServiceReviewService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/review",
    tags=["review"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/batches")
async def create_batch(
    command: ReviewBatchCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    record = await service.create_batch(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/batches")
async def list_batches(
    workspace_id: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    records = await service.list_batches(
        workspace_id=workspace_id,
        execution_id=execution_id,
        status=status,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    record = await service.get_batch(batch_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/items")
async def list_items(
    workspace_id: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    target_domain: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    records = await service.list_items(
        workspace_id=workspace_id,
        execution_id=execution_id,
        target_domain=target_domain,
        target_kind=target_kind,
        status=status,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.patch("/items/{item_id}/decision")
async def set_item_decision(
    item_id: str,
    command: ReviewItemDecisionCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    record = await service.set_item_decision(item_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/items/{item_id}/transition")
async def transition_item(
    item_id: str,
    command: ReviewItemTransitionCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceReviewService(uow.required_session, autocommit=False)
    record = await service.apply_item(item_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)
