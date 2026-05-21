"""Source and provenance endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.service import ProvenanceDataDomainService
from src.dataservice.domains.source.contracts import (
    SourceCitationUsageCreateCommand,
    SourceCreateCommand,
)
from src.dataservice.domains.source.service import SourceDataDomainService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1",
    tags=["source"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/sources")
async def create_source(
    command: SourceCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.create_source(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/sources")
async def list_sources(
    workspace_id: str = Query(),
    library_status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_sources(
        workspace_id=workspace_id,
        library_status=library_status,
        include_deleted=include_deleted,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.post("/sources/citation-usage")
async def record_source_citation_usage(
    command: SourceCitationUsageCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.record_citation_usage(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_source(source_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/provenance/links")
async def create_provenance_link(
    command: ProvenanceLinkCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = ProvenanceDataDomainService(uow.required_session, autocommit=False)
    record = await service.create_link(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/provenance/links")
async def list_provenance_links(
    workspace_id: str = Query(),
    source_id: str | None = Query(default=None),
    target_domain: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    review_item_id: str | None = Query(default=None),
    relation_kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = ProvenanceDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_links(
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


@router.delete("/provenance/links")
async def delete_provenance_links(
    workspace_id: str = Query(),
    source_id: str | None = Query(default=None),
    target_domain: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    review_item_id: str | None = Query(default=None),
    relation_kind: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = ProvenanceDataDomainService(uow.required_session, autocommit=False)
    deleted = await service.delete_links(
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
