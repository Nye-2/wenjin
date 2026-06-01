"""DataService source and provenance domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.models import ProvenanceLinkRecord, SourceAnchorRecord
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
from src.dataservice.domains.source.models import SourceAssetRecord, SourceRecord
from src.dataservice.domains.source.service import SourceDataDomainService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _record(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {"created_at": now, "updated_at": now}
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeSourceRepository:
    def __init__(self) -> None:
        self.sources: dict[str, SimpleNamespace] = {}
        self.external_ids: list[SimpleNamespace] = []
        self.outline_nodes: list[SimpleNamespace] = []
        self.text_units: list[SimpleNamespace] = []
        self.source_assets: list[SimpleNamespace] = []
        self.bibtex_snapshots: list[SimpleNamespace] = []

    def create_source(self, values: dict[str, Any]) -> SimpleNamespace:
        source_id = str(values.pop("source_id", None) or f"source-{len(self.sources) + 1}")
        record = _record(
            {
                "id": source_id,
                "verified_at": None,
                "is_deleted": False,
                **values,
            }
        )
        self.sources[source_id] = record
        return record

    def create_outline_node(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": values.pop("id", f"node-{len(self.outline_nodes) + 1}"), **values})
        self.outline_nodes.append(record)
        return record

    def create_text_unit(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": values.pop("id", f"unit-{len(self.text_units) + 1}"), **values})
        self.text_units.append(record)
        return record

    def create_source_asset(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": values.pop("id", f"asset-{len(self.source_assets) + 1}"), **values})
        self.source_assets.append(record)
        return record

    def create_external_id(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": values.pop("id", f"external-{len(self.external_ids) + 1}"), **values})
        self.external_ids.append(record)
        return record

    def create_bibtex_snapshot(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": values.pop("id", f"snapshot-{len(self.bibtex_snapshots) + 1}"), **values})
        self.bibtex_snapshots.append(record)
        return record

    async def get_external_id(
        self,
        *,
        workspace_id: str,
        provider: str,
        external_id: str,
    ) -> SimpleNamespace | None:
        return next(
            (
                record
                for record in self.external_ids
                if record.workspace_id == workspace_id
                and record.provider == provider
                and record.external_id == external_id
            ),
            None,
        )

    async def list_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[SimpleNamespace]:
        return [
            record
            for record in self.external_ids
            if record.workspace_id == workspace_id and record.source_id == source_id
        ]

    async def get_source_asset(self, source_asset_id: str) -> SimpleNamespace | None:
        return next((record for record in self.source_assets if record.id == source_asset_id), None)

    async def get_source(self, source_id: str) -> SimpleNamespace | None:
        return self.sources.get(source_id)

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ) -> SimpleNamespace | None:
        record = self.sources.get(source_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        if not include_deleted and record.is_deleted:
            return None
        return record

    async def list_sources_by_ids(
        self,
        *,
        workspace_id: str,
        source_ids: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SimpleNamespace]:
        records = [
            record
            for record in self.sources.values()
            if record.workspace_id == workspace_id and record.id in source_ids
        ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        if not include_excluded:
            records = [record for record in records if record.library_status != "excluded"]
        return records

    async def find_source_by_doi(
        self,
        *,
        workspace_id: str,
        doi: str,
        include_deleted: bool = False,
    ) -> SimpleNamespace | None:
        return next(
            (
                record
                for record in self.sources.values()
                if record.workspace_id == workspace_id
                and record.doi == doi
                and (include_deleted or not record.is_deleted)
            ),
            None,
        )

    async def find_source_by_title_year(
        self,
        *,
        workspace_id: str,
        normalized_title: str,
        year: int | None,
        include_deleted: bool = False,
    ) -> SimpleNamespace | None:
        return next(
            (
                record
                for record in self.sources.values()
                if record.workspace_id == workspace_id
                and record.normalized_title == normalized_title
                and (year is None or record.year == year)
                and (include_deleted or not record.is_deleted)
            ),
            None,
        )

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.sources.values() if record.workspace_id == workspace_id]
        if library_status is not None:
            records = [record for record in records if record.library_status == library_status]
        elif not include_excluded:
            records = [record for record in records if record.library_status != "excluded"]
        if source_kind is not None:
            records = [record for record in records if record.source_kind == source_kind]
        if ingest_kind is not None:
            records = [record for record in records if record.ingest_kind == ingest_kind]
        if query and query.strip():
            normalized = query.strip().lower()
            records = [
                record
                for record in records
                if normalized in record.title.lower()
                or normalized in str(record.venue or "").lower()
                or normalized in str(record.doi or "").lower()
                or normalized in str(record.abstract or "").lower()
                or normalized in record.citation_key.lower()
            ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        return records[offset : offset + limit]

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        fulltext_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        records = [record for record in self.sources.values() if record.workspace_id == workspace_id]
        if library_status is not None:
            records = [record for record in records if record.library_status == library_status]
        elif not include_excluded:
            records = [record for record in records if record.library_status != "excluded"]
        if source_kind is not None:
            records = [record for record in records if record.source_kind == source_kind]
        if ingest_kind is not None:
            records = [record for record in records if record.ingest_kind == ingest_kind]
        if fulltext_status is not None:
            records = [record for record in records if record.fulltext_status == fulltext_status]
        if query and query.strip():
            normalized = query.strip().lower()
            records = [
                record
                for record in records
                if normalized in record.title.lower()
                or normalized in str(record.venue or "").lower()
                or normalized in str(record.doi or "").lower()
                or normalized in str(record.abstract or "").lower()
                or normalized in record.citation_key.lower()
            ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        return len(records)

    async def citation_key_exists(
        self,
        *,
        workspace_id: str,
        citation_key: str,
        exclude_source_id: str | None = None,
    ) -> bool:
        return any(
            record.workspace_id == workspace_id
            and record.citation_key == citation_key
            and not record.is_deleted
            and record.id != exclude_source_id
            for record in self.sources.values()
        )

    async def list_outline_nodes(
        self,
        *,
        workspace_id: str,
        source_id: str,
        limit: int = 200,
    ) -> list[SimpleNamespace]:
        return [
            record
            for record in self.outline_nodes
            if record.workspace_id == workspace_id and record.source_id == source_id
        ][:limit]

    async def delete_source_index(self, *, workspace_id: str, source_id: str) -> None:
        self.outline_nodes = [
            record
            for record in self.outline_nodes
            if not (record.workspace_id == workspace_id and record.source_id == source_id)
        ]
        self.text_units = [
            record
            for record in self.text_units
            if not (record.workspace_id == workspace_id and record.source_id == source_id)
        ]

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 12,
    ) -> list[SimpleNamespace]:
        normalized = query.strip().lower()
        records = [
            record
            for record in self.text_units
            if record.workspace_id == workspace_id and normalized in record.search_text.lower()
        ]
        if source_ids:
            records = [record for record in records if record.source_id in source_ids]
        return records[:limit]

    async def list_source_assets(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[tuple[SimpleNamespace, SimpleNamespace | None]]:
        return [
            (record, None)
            for record in self.source_assets
            if record.workspace_id == workspace_id and record.source_id == source_id
        ]

    async def list_sources_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SimpleNamespace]:
        records = [
            record
            for record in self.sources.values()
            if record.workspace_id == workspace_id and record.citation_key in citation_keys
        ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        if not include_excluded:
            records = [record for record in records if record.library_status != "excluded"]
        return records


class FakeProvenanceRepository:
    def __init__(self) -> None:
        self.links: list[SimpleNamespace] = []

    def create_link(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": f"link-{len(self.links) + 1}", **values})
        self.links.append(record)
        return record

    async def list_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.links if record.workspace_id == workspace_id]
        if source_id is not None:
            records = [record for record in records if record.source_id == source_id]
        if target_domain is not None:
            records = [record for record in records if record.target_domain == target_domain]
        if target_kind is not None:
            records = [record for record in records if record.target_kind == target_kind]
        if target_id is not None:
            records = [record for record in records if record.target_id == target_id]
        if review_item_id is not None:
            records = [record for record in records if record.review_item_id == review_item_id]
        if relation_kind is not None:
            records = [record for record in records if record.relation_kind == relation_kind]
        return records[:limit]

    async def delete_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
    ) -> int:
        before = len(self.links)
        records = await self.list_links(
            workspace_id=workspace_id,
            source_id=source_id,
            target_domain=target_domain,
            target_kind=target_kind,
            target_id=target_id,
            review_item_id=review_item_id,
            relation_kind=relation_kind,
            limit=len(self.links) or 1,
        )
        delete_ids = {record.id for record in records}
        self.links = [record for record in self.links if record.id not in delete_ids]
        return before - len(self.links)


def test_source_and_provenance_models_are_registered_on_shared_metadata() -> None:
    assert SourceRecord.__tablename__ in Base.metadata.tables
    assert SourceAssetRecord.__tablename__ in Base.metadata.tables
    assert SourceAnchorRecord.__tablename__ in Base.metadata.tables
    assert ProvenanceLinkRecord.__tablename__ in Base.metadata.tables


@pytest.mark.asyncio
async def test_source_service_normalizes_title_and_lists_active_sources() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    created = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="  Attention Is All You Need  ",
            citation_key="vaswani2017",
            authors_json=["Vaswani"],
            library_status="included",
        )
    )
    listed = await service.list_sources(workspace_id="ws-1", library_status="included")

    assert created.normalized_title == "attention is all you need"
    assert listed[0].citation_key == "vaswani2017"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_source_service_counts_sources_by_library_status() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    for citation_key, status in (
        ("core2026", "core"),
        ("included2026", "included"),
        ("excluded2026", "excluded"),
    ):
        await service.create_source(
            SourceCreateCommand(
                workspace_id="ws-1",
                title=citation_key,
                citation_key=citation_key,
                library_status=status,
            )
        )

    assert await service.count_sources(workspace_id="ws-1") == 2
    assert await service.count_sources(workspace_id="ws-1", library_status="core") == 1
    assert await service.count_sources(workspace_id="ws-1", include_excluded=True) == 3


@pytest.mark.asyncio
async def test_source_service_lists_reference_page_with_ingest_filter() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Uploaded Paper",
            citation_key="uploaded2026",
            ingest_kind="upload",
            library_status="included",
            fulltext_status="indexed",
        )
    )
    await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Manual Paper",
            citation_key="manual2026",
            ingest_kind="manual",
            library_status="core",
        )
    )

    page = await service.list_sources_page(
        workspace_id="ws-1",
        ingest_kind="upload",
        query="uploaded",
    )
    summary = await service.count_reference_summary("ws-1")

    assert [item["citation_key"] for item in page["items"]] == ["uploaded2026"]
    assert page["total"] == 1
    assert page["core_count"] == 1
    assert summary == {"total": 2, "core": 1, "indexed": 1}


@pytest.mark.asyncio
async def test_source_service_upserts_with_explicit_source_id() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    created = await service.upsert_source(
        SourceCreateCommand(
            source_id="reference-1",
            workspace_id="ws-1",
            title="Original",
            citation_key="original2026",
        )
    )
    updated = await service.upsert_source(
        SourceCreateCommand(
            source_id="reference-1",
            workspace_id="ws-1",
            title="Updated",
            citation_key="updated2026",
            library_status="included",
        )
    )

    assert created.id == "reference-1"
    assert updated.id == "reference-1"
    assert updated.title == "Updated"
    assert updated.library_status == "included"
    assert len(repository.sources) == 1


@pytest.mark.asyncio
async def test_source_service_updates_and_deletes_reference_state() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    first = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="First Paper",
            citation_key="paper2026",
            library_status="included",
        )
    )
    second = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Second Paper",
            citation_key="other2026",
        )
    )

    updated = await service.update_source(
        workspace_id="ws-1",
        source_id=second.id,
        command=SourceUpdateCommand(
            title="Second Paper Revised",
            citation_key=first.citation_key,
            library_status="core",
            tags_json=["important"],
        ),
    )
    deleted = await service.mark_deleted_for_workspace(workspace_id="ws-1", source_id=first.id)

    assert updated is not None
    assert updated.normalized_title == "second paper revised"
    assert updated.citation_key == "paper20262"
    assert updated.library_status == "core"
    assert updated.tags_json == ["important"]
    assert deleted is True
    assert await service.get_source_for_workspace(workspace_id="ws-1", source_id=first.id) is None


@pytest.mark.asyncio
async def test_source_service_upserts_external_ids_into_detail() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="External Paper",
            citation_key="external2026",
            library_status="included",
        )
    )
    first = await service.upsert_source_external_ids(
        workspace_id="ws-1",
        source_id=source.id,
        external_ids=[
            SourceExternalIdCreateCommand(
                provider="semantic_scholar",
                external_id="paper-1",
                url="https://example.test/paper-1",
            )
        ],
    )
    second = await service.upsert_source_external_ids(
        workspace_id="ws-1",
        source_id=source.id,
        external_ids=[
            SourceExternalIdCreateCommand(
                provider="semantic_scholar",
                external_id="paper-1",
                metadata_json={"source_label": "verified"},
            )
        ],
    )
    detail = await service.get_source_detail(workspace_id="ws-1", source_id=source.id)

    assert first[0]["external_id"] == "paper-1"
    assert second[0]["url"] == "https://example.test/paper-1"
    assert second[0]["metadata"] == {"source_label": "verified"}
    assert detail is not None
    assert detail["external_ids"] == second
    assert len(repository.external_ids) == 1


@pytest.mark.asyncio
async def test_source_service_imports_and_dedupes_by_external_id() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    first = await service.import_source(
        SourceImportCommand(
            workspace_id="ws-1",
            title="Imported Paper",
            citation_key="imported2026",
            authors_json=["Ada"],
            year=2026,
            doi="https://doi.org/10.1000/example",
            ingest_kind="semantic_scholar",
            library_status="candidate",
            evidence_level="external_verified",
            external_ids=[
                SourceExternalIdCreateCommand(
                    provider="semantic_scholar",
                    external_id="paper-1",
                )
            ],
        )
    )
    second = await service.import_source(
        SourceImportCommand(
            workspace_id="ws-1",
            title="Imported Paper Revised",
            citation_key="imported2026",
            authors_json=["Ada"],
            year=2026,
            doi="10.1000/example",
            ingest_kind="semantic_scholar",
            library_status="included",
            evidence_level="external_verified",
            external_ids=[
                SourceExternalIdCreateCommand(
                    provider="semantic_scholar",
                    external_id="paper-1",
                    url="https://example.test/paper-1",
                )
            ],
        )
    )

    assert first.created is True
    assert second.created is False
    assert second.source.id == first.source.id
    assert second.source.library_status == "included"
    assert second.external_ids[0]["url"] == "https://example.test/paper-1"
    assert len(repository.sources) == 1


@pytest.mark.asyncio
async def test_source_service_replaces_source_index() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Indexed Paper",
            citation_key="indexed2026",
            fulltext_status="uploaded",
            evidence_level="uploaded_fulltext",
        )
    )
    result = await service.replace_source_index(
        workspace_id="ws-1",
        source_id=source.id,
        outline_nodes=[
            {
                "id": "node-1",
                "workspace_id": "ws-1",
                "source_id": source.id,
                "parent_id": None,
                "section_path": "1",
                "title": "Introduction",
                "level": 1,
                "sort_order": 0,
                "page_start": 1,
                "page_end": 1,
                "char_start": 0,
                "char_end": 50,
                "summary": "Intro",
                "keywords_json": ["intro"],
            }
        ],
        text_units=[
            {
                "id": "unit-1",
                "workspace_id": "ws-1",
                "source_id": source.id,
                "outline_node_id": "node-1",
                "source_asset_id": "asset-1",
                "unit_type": "section",
                "unit_index": 0,
                "content": "Indexed content",
                "search_text": "Indexed Paper\nIntroduction\nIndexed content",
                "token_count": 2,
                "page_start": 1,
                "page_end": 1,
                "char_start": 0,
                "char_end": 50,
                "metadata_json": {"section_path": "1"},
            }
        ],
    )
    updated = await service.get_source_for_workspace(workspace_id="ws-1", source_id=source.id)

    assert result == {"outline_nodes": 1, "text_units": 1}
    assert len(repository.outline_nodes) == 1
    assert len(repository.text_units) == 1
    assert updated is not None
    assert updated.fulltext_status == "indexed"
    assert updated.evidence_level == "indexed_fulltext"


@pytest.mark.asyncio
async def test_source_service_builds_evidence_pack_from_source_index() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Grounded Evidence",
            citation_key="grounded2026",
            library_status="included",
            fulltext_status="uploaded",
            evidence_level="uploaded_fulltext",
        )
    )
    excluded = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Excluded Evidence",
            citation_key="excluded2026",
            library_status="excluded",
        )
    )
    await service.replace_source_index(
        workspace_id="ws-1",
        source_id=source.id,
        outline_nodes=[
            {
                "id": "node-1",
                "workspace_id": "ws-1",
                "source_id": source.id,
                "parent_id": None,
                "section_path": "1",
                "title": "Method",
                "level": 1,
                "sort_order": 0,
                "page_start": 1,
                "page_end": 2,
                "char_start": 0,
                "char_end": 100,
                "summary": "Grounded method",
                "keywords_json": ["method"],
            }
        ],
        text_units=[
            {
                "id": "unit-1",
                "workspace_id": "ws-1",
                "source_id": source.id,
                "outline_node_id": "node-1",
                "source_asset_id": "asset-1",
                "unit_type": "section",
                "unit_index": 0,
                "content": "Grounded evidence content",
                "search_text": "Grounded Evidence\nMethod\nGrounded evidence content",
                "token_count": 3,
                "page_start": 1,
                "page_end": 2,
                "char_start": 0,
                "char_end": 100,
                "metadata_json": {"section_path": "1"},
            }
        ],
    )

    pack = await service.build_evidence_pack(
        SourceEvidencePackCreateCommand(
            workspace_id="ws-1",
            query="grounded",
            source_ids=[source.id, excluded.id],
            max_units=4,
        )
    )

    assert pack.policy == "outline_first_no_vector_rag"
    assert [item["source"]["citation_key"] for item in pack.library_outline] == ["grounded2026"]
    assert [unit["id"] for unit in pack.selected_units] == ["unit-1"]
    assert pack.selected_units[0]["source_id"] == source.id


@pytest.mark.asyncio
async def test_source_service_links_source_assets() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Asset Paper",
            citation_key="asset2026",
        )
    )
    linked = await service.link_source_asset(
        workspace_id="ws-1",
        source_id=source.id,
        workspace_asset_id="workspace-asset-1",
        source_asset_id="source-asset-1",
        asset_type="pdf",
        preprocess_status="pending",
        metadata_json={"virtual_path": "references/paper.pdf"},
    )
    assets = await service.list_source_assets(workspace_id="ws-1", source_id=source.id)

    assert linked["id"] == "source-asset-1"
    assert assets[0]["workspace_asset_id"] == "workspace-asset-1"
    assert assets[0]["asset_type"] == "pdf"
    assert assets[0]["virtual_path"] == "references/paper.pdf"


@pytest.mark.asyncio
async def test_source_service_rejects_cross_workspace_source_asset_relink() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Original Asset Paper",
            citation_key="assetoriginal2026",
        )
    )
    await service.link_source_asset(
        workspace_id="ws-1",
        source_id=source.id,
        workspace_asset_id="workspace-asset-1",
        source_asset_id="source-asset-1",
        asset_type="pdf",
        preprocess_status="pending",
    )
    other_source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-2",
            title="Other Asset Paper",
            citation_key="assetother2026",
        )
    )

    with pytest.raises(DataServiceValidationError, match="source asset does not belong"):
        await service.link_source_asset(
            workspace_id="ws-2",
            source_id=other_source.id,
            workspace_asset_id="workspace-asset-2",
            source_asset_id="source-asset-1",
            asset_type="pdf",
            preprocess_status="pending",
        )

    asset = await service.get_source_asset(
        workspace_id="ws-1",
        source_asset_id="source-asset-1",
    )
    assert asset is not None
    assert asset["workspace_id"] == "ws-1"
    assert asset["source_id"] == source.id
    assert asset["workspace_asset_id"] == "workspace-asset-1"


@pytest.mark.asyncio
async def test_source_service_updates_source_asset_status_and_metadata() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    source = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Asset Status Paper",
            citation_key="assetstatus2026",
        )
    )
    await service.link_source_asset(
        workspace_id="ws-1",
        source_id=source.id,
        workspace_asset_id="workspace-asset-1",
        source_asset_id="source-asset-1",
        asset_type="pdf",
        preprocess_status="pending",
        metadata_json={"virtual_path": "references/paper.pdf"},
    )

    updated = await service.update_source_asset(
        workspace_id="ws-1",
        source_asset_id="source-asset-1",
        command=SourceAssetUpdateCommand(
            preprocess_status="succeeded",
            metadata_json={"manifest_path": "references/manifest.json"},
        ),
    )

    assert updated is not None
    assert updated["preprocess_status"] == "succeeded"
    assert updated["manifest_path"] == "references/manifest.json"
    assert updated["metadata"]["virtual_path"] == "references/paper.pdf"


@pytest.mark.asyncio
async def test_source_service_builds_bibliography_from_sources() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    first = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="First Paper",
            citation_key="first2026",
            authors_json=["First Author"],
            year=2026,
            venue="Test Journal",
            library_status="included",
        )
    )
    second = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Second Paper",
            citation_key="second2026",
            authors_json=["Second Author"],
            bibtex_entry_type="inproceedings",
            bibtex_fields_json={"note": "Accepted"},
            library_status="included",
        )
    )

    bibliography = await service.build_bibliography(
        SourceBibliographyCreateCommand(
            workspace_id="ws-1",
            source_ids=[second.id, first.id],
        )
    )

    assert bibliography.count == 2
    assert bibliography.source_ids == [second.id, first.id]
    assert bibliography.citation_keys == ["second2026", "first2026"]
    assert bibliography.content is not None
    assert bibliography.content.index("@inproceedings{second2026") < bibliography.content.index(
        "@article{first2026"
    )
    assert "author = {First Author}" in bibliography.content
    assert "journal = {Test Journal}" in bibliography.content
    assert "note = {Accepted}" in bibliography.content


@pytest.mark.asyncio
async def test_source_service_creates_bibliography_snapshot() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSourceRepository()
    service.repository = repository  # type: ignore[assignment]

    snapshot = await service.create_bibliography_snapshot(
        SourceBibliographySnapshotCreateCommand(
            workspace_id="ws-1",
            prism_project_id="latex-1",
            scope="used_only",
            content="@article{lovelace2026}",
            reference_count=1,
            checksum="checksum-1",
        )
    )

    assert snapshot.id == "snapshot-1"
    assert snapshot.workspace_id == "ws-1"
    assert snapshot.prism_project_id == "latex-1"
    assert snapshot.scope == "used_only"
    assert snapshot.reference_count == 1
    assert repository.bibtex_snapshots[0].content == "@article{lovelace2026}"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_provenance_service_creates_and_filters_links() -> None:
    session = FakeSession()
    service = ProvenanceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeProvenanceRepository()
    service.repository = repository  # type: ignore[assignment]

    created = await service.create_link(
        ProvenanceLinkCreateCommand(
            workspace_id="ws-1",
            source_id="source-1",
            target_domain="prism",
            target_kind="file",
            target_id="file-1",
            relation_kind="cited",
            citation_key="vaswani2017",
        )
    )
    listed = await service.list_links(
        workspace_id="ws-1",
        target_domain="prism",
        target_kind="file",
        relation_kind="cited",
    )
    deleted = await service.delete_links(
        workspace_id="ws-1",
        target_domain="prism",
        target_kind="file",
        relation_kind="cited",
    )

    assert created.id == "link-1"
    assert listed[0].source_id == "source-1"
    assert deleted == 1
    assert repository.links == []
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_source_service_records_citation_usage_as_provenance() -> None:
    session = FakeSession()
    service = SourceDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    source_repository = FakeSourceRepository()
    provenance_repository = FakeProvenanceRepository()
    service.repository = source_repository  # type: ignore[assignment]
    service.provenance_repository = provenance_repository  # type: ignore[assignment]

    created = await service.create_source(
        SourceCreateCommand(
            workspace_id="ws-1",
            title="Tracing Sources",
            citation_key="smith2026",
            library_status="included",
        )
    )
    usage = await service.record_citation_usage(
        SourceCitationUsageCreateCommand(
            workspace_id="ws-1",
            citation_keys=["smith2026", "missing2026", "smith2026"],
            latex_project_id="latex-1",
            target_id="latex-1",
            target_section="sections/intro.tex",
            target_ref_json={"file_path": "sections/intro.tex"},
            generated_text=r"Claim \cite{smith2026}.",
            accepted_status="accepted",
        )
    )

    assert usage.recorded == 1
    assert usage.source_ids == [created.id]
    assert usage.citation_keys == ["smith2026"]
    assert usage.provenance_link_ids == ["link-1"]
    assert source_repository.sources[created.id].library_status == "used_in_draft"
    assert provenance_repository.links[0].target_domain == "prism"
    assert provenance_repository.links[0].target_kind == "prism_file"
    assert provenance_repository.links[0].target_id == "latex-1"
    assert provenance_repository.links[0].target_ref_json == {
        "file_path": "sections/intro.tex",
        "latex_project_id": "latex-1",
        "target_section": "sections/intro.tex",
        "citation_key": "smith2026",
    }
    assert provenance_repository.links[0].metadata_json["accepted_status"] == "accepted"
    assert session.commit_count == 2
