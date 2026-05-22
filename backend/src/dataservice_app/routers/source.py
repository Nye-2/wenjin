"""Source and provenance endpoints for DataService internal API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

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
    SourceEvidencePackCreateCommand,
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


class SourceAssetLinkRequest(BaseModel):
    workspace_id: str
    source_id: str
    workspace_asset_id: str
    asset_type: str
    source_asset_id: str | None = None
    preprocess_status: str = "skipped"
    manifest_asset_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SourceIndexReplaceRequest(BaseModel):
    workspace_id: str
    source_id: str
    outline_nodes: list[dict[str, Any]] = Field(default_factory=list)
    text_units: list[dict[str, Any]] = Field(default_factory=list)


class SourceStatusUpdateRequest(BaseModel):
    library_status: str | None = None
    read_status: str | None = None


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


@router.get("/sources/page")
async def list_sources_page(
    workspace_id: str = Query(),
    library_status: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    ingest_kind: str | None = Query(default=None),
    query: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=5000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.list_sources_page(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            offset=offset,
            limit=limit,
        )
    )


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
    source_ids: list[str] | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=50),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.search_text_units(
            workspace_id=workspace_id,
            query=query,
            source_ids=source_ids,
            limit=limit,
        )
    )


@router.post("/sources/evidence-pack")
async def build_source_evidence_pack(
    command: SourceEvidencePackCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.build_evidence_pack(command)
    return envelope_ok(record.model_dump(mode="json"))


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


@router.get("/sources/{source_id}/workspace-record")
async def get_source_for_workspace(
    source_id: str,
    workspace_id: str = Query(),
    include_deleted: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_source_for_workspace(
        workspace_id=workspace_id,
        source_id=source_id,
        include_deleted=include_deleted,
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/sources/{source_id}/assets")
async def list_source_assets(
    source_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(await service.list_source_assets(workspace_id=workspace_id, source_id=source_id))


@router.get("/sources/{source_id}/outline")
async def get_source_outline(
    source_id: str,
    workspace_id: str = Query(),
    limit: int = Query(default=200, ge=1, le=5000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(await service.get_source_outline(workspace_id, source_id, limit=limit))


@router.get("/sources/{source_id}/outline/{outline_node_id}/content")
async def read_source_outline_node(
    source_id: str,
    outline_node_id: str,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.read_source_outline_node(
            workspace_id=workspace_id,
            source_id=source_id,
            outline_node_id=outline_node_id,
        )
    )


@router.get("/sources/{source_id}/pages")
async def read_source_pages(
    source_id: str,
    workspace_id: str = Query(),
    page_start: int = Query(ge=1),
    page_end: int = Query(ge=1),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    return envelope_ok(
        await service.read_source_pages(
            workspace_id=workspace_id,
            source_id=source_id,
            page_start=page_start,
            page_end=page_end,
        )
    )


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


@router.post("/source-assets")
async def link_source_asset(
    command: SourceAssetLinkRequest,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.link_source_asset(
        workspace_id=command.workspace_id,
        source_id=command.source_id,
        workspace_asset_id=command.workspace_asset_id,
        asset_type=command.asset_type,
        source_asset_id=command.source_asset_id,
        preprocess_status=command.preprocess_status,
        manifest_asset_id=command.manifest_asset_id,
        metadata_json=command.metadata_json,
    )
    await uow.commit()
    return envelope_ok(record)


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


@router.put("/sources/{source_id}/index")
async def replace_source_index(
    source_id: str,
    command: SourceIndexReplaceRequest,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.replace_source_index(
        workspace_id=command.workspace_id,
        source_id=source_id,
        outline_nodes=command.outline_nodes,
        text_units=command.text_units,
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


@router.patch("/sources/{source_id}/status")
async def mark_source_status(
    source_id: str,
    command: SourceStatusUpdateRequest,
    workspace_id: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SourceDataDomainService(uow.required_session, autocommit=False)
    record = await service.mark_status(
        workspace_id=workspace_id,
        source_id=source_id,
        library_status=command.library_status,
        read_status=command.read_status,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


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
