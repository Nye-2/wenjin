"""Prism review endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.prism_review_api import PrismReviewDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.prism_review import (
    PrismFileChangeAppliedPayload,
    PrismFileChangeClearPayload,
    PrismFileChangeRejectedPayload,
    PrismFileChangeUpsertPayload,
)

router = APIRouter(
    prefix="/internal/v1/prism-review",
    tags=["prism-review"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/file-changes/find")
async def find_file_change(
    workspace_id: str,
    latex_project_id: str,
    logical_key: str,
    statuses: list[str] | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=2000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    item = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).find_file_change(
        workspace_id=workspace_id,
        latex_project_id=latex_project_id,
        logical_key=logical_key,
        statuses=tuple(statuses) if statuses is not None else None,
        limit=limit,
    )
    return envelope_ok(item.model_dump(mode="json") if item else None)


@router.post("/file-changes/upsert")
async def upsert_pending_file_change(
    payload: PrismFileChangeUpsertPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    item = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).upsert_pending_file_change(**payload.model_dump())
    await uow.commit()
    return envelope_ok(item.model_dump(mode="json"))


@router.post("/file-changes/clear-pending")
async def clear_pending_file_change(
    payload: PrismFileChangeClearPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deleted = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).clear_pending_file_change(**payload.model_dump())
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.post("/items/{item_id}/applied")
async def mark_applied_file_change(
    item_id: str,
    payload: PrismFileChangeAppliedPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    item = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).mark_applied_file_change(item_id, **payload.model_dump())
    await uow.commit()
    return envelope_ok(item.model_dump(mode="json") if item else None)


@router.post("/items/{item_id}/rejected")
async def mark_rejected_file_change(
    item_id: str,
    payload: PrismFileChangeRejectedPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    item = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).mark_rejected_file_change(item_id, reason=payload.reason)
    await uow.commit()
    return envelope_ok(item.model_dump(mode="json") if item else None)


@router.post("/items/{item_id}/reverted")
async def mark_reverted_file_change(
    item_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    item = await PrismReviewDataService(
        uow.required_session,
        autocommit=False,
    ).mark_reverted_file_change(item_id)
    await uow.commit()
    return envelope_ok(item.model_dump(mode="json") if item else None)
