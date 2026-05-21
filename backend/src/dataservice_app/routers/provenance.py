"""Provenance endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.provenance_api import ProvenanceDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.provenance import ProvenanceLinkCreatePayload

router = APIRouter(
    prefix="/internal/v1/provenance",
    tags=["provenance"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/links")
async def create_link(
    payload: ProvenanceLinkCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await ProvenanceDataService(
        uow.required_session,
        autocommit=False,
    ).create_link(ProvenanceLinkCreateCommand(**payload.model_dump(mode="json")))
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/links")
async def list_links(
    workspace_id: str = Query(),
    source_id: str | None = Query(default=None),
    target_domain: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    review_item_id: str | None = Query(default=None),
    relation_kind: str | None = Query(default=None),
    limit: int = Query(default=50),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    records = await ProvenanceDataService(
        uow.required_session,
        autocommit=False,
    ).list_links(
        workspace_id=workspace_id,
        source_id=source_id,
        target_domain=target_domain,
        target_kind=target_kind,
        target_id=target_id,
        review_item_id=review_item_id,
        relation_kind=relation_kind,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.delete("/links")
async def delete_links(
    workspace_id: str = Query(),
    source_id: str | None = Query(default=None),
    target_domain: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    review_item_id: str | None = Query(default=None),
    relation_kind: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deleted = await ProvenanceDataService(
        uow.required_session,
        autocommit=False,
    ).delete_links(
        workspace_id=workspace_id,
        source_id=source_id,
        target_domain=target_domain,
        target_kind=target_kind,
        target_id=target_id,
        review_item_id=review_item_id,
        relation_kind=relation_kind,
    )
    await uow.commit()
    return envelope_ok({"deleted": deleted})
