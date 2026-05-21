"""Source and provenance endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.service import ProvenanceDataDomainService
from src.dataservice.domains.source.contracts import (
    SourceAssetUpdateCommand,
    SourceBibliographyCreateCommand,
    SourceBibliographySnapshotCreateCommand,
    SourceCitationUsageCreateCommand,
    SourceCreateCommand,
    SourceExternalIdCreateCommand,
    SourceImportCommand,
    SourceUpdateCommand,
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


@router.post("/sources/upsert")
async def upsert_source(
    command: SourceCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.upsert_source(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/sources/import")
async def import_source(
    command: SourceImportCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.import_source(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/sources")
async def list_sources(
    workspace_id: str = Query(),
    library_status: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    ingest_kind: str | None = Query(default=None),
    query: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    include_excluded: bool = Query(default=True),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=5000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_sources(
        workspace_id=workspace_id,
        library_status=library_status,
        source_kind=source_kind,
        ingest_kind=ingest_kind,
        query=query,
        include_deleted=include_deleted,
        include_excluded=include_excluded,
        offset=offset,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/sources/count")
async def count_sources(
    workspace_id: str = Query(),
    library_status: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    ingest_kind: str | None = Query(default=None),
    query: str | None = Query(default=None),
    fulltext_status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    include_excluded: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    count = await service.count_sources(
        workspace_id=workspace_id,
        library_status=library_status,
        source_kind=source_kind,
        ingest_kind=ingest_kind,
        query=query,
        fulltext_status=fulltext_status,
        include_deleted=include_deleted,
        include_excluded=include_excluded,
    )
    return envelope_ok({"count": count})


@router.get("/sources/count/reference-summary")
async def count_source_reference_summary(
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(await service.count_reference_summary(workspace_id))


@router.get("/sources/library-outline")
async def get_source_library_outline(
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(await service.get_library_outline(workspace_id))


@router.get("/sources/toc-summary")
async def get_source_toc_summary(
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok({"summary": await service.get_workspace_toc_summary(workspace_id)})


@router.get("/sources/text-units/search")
async def search_source_text_units(
    workspace_id: str = Query(),
    query: str = Query(),
    limit: int = Query(default=8, ge=1, le=50),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.search_workspace_sections(workspace_id, query, limit=limit)
    )


@router.post("/sources/citation-usage")
async def record_source_citation_usage(
    command: SourceCitationUsageCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.record_citation_usage(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/sources/bibliography")
async def build_source_bibliography(
    command: SourceBibliographyCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.build_bibliography(command)
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/sources/bibliography/snapshots")
async def create_source_bibliography_snapshot(
    command: SourceBibliographySnapshotCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.create_bibliography_snapshot(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/sources/{source_id}/sections/by-path")
async def get_source_section_by_path(
    source_id: str,
    workspace_id: str = Query(),
    section_path: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    section = await service.get_source_section(
        workspace_id=workspace_id,
        source_id=source_id,
        section_path=section_path,
    )
    return envelope_ok(section)


@router.get("/sources/{source_id}/sections/by-title")
async def get_source_section_by_title(
    source_id: str,
    workspace_id: str = Query(),
    section_title: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    section = await service.get_source_section_by_title(
        workspace_id=workspace_id,
        source_id=source_id,
        section_title=section_title,
    )
    return envelope_ok(section)


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_source(source_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/sources/{source_id}/detail")
async def get_source_detail(
    source_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(await service.get_source_detail(workspace_id=workspace_id, source_id=source_id))


@router.get("/source-assets/{source_asset_id}")
async def get_source_asset(
    source_asset_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.get_source_asset(workspace_id=workspace_id, source_asset_id=source_asset_id)
    )


@router.patch("/source-assets/{source_asset_id}")
async def update_source_asset(
    source_asset_id: str,
    command: SourceAssetUpdateCommand,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.update_source_asset(
        workspace_id=workspace_id,
        source_asset_id=source_asset_id,
        command=command,
    )
    await uow.commit()
    return envelope_ok(record)


@router.post("/sources/{source_id}/external-ids")
async def upsert_source_external_ids(
    source_id: str,
    command: list[SourceExternalIdCreateCommand],
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    records = await service.upsert_source_external_ids(
        workspace_id=workspace_id,
        source_id=source_id,
        external_ids=command,
    )
    await uow.commit()
    return envelope_ok(records)


@router.get("/sources/{source_id}/external-ids")
async def list_source_external_ids(
    source_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.list_source_external_ids(workspace_id=workspace_id, source_id=source_id)
    )


@router.patch("/sources/{source_id}")
async def update_source(
    source_id: str,
    command: SourceUpdateCommand,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.update_source(
        workspace_id=workspace_id,
        source_id=source_id,
        command=command,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    deleted = await service.mark_deleted_for_workspace(workspace_id=workspace_id, source_id=source_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})


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
