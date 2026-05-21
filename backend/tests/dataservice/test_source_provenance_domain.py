"""DataService source and provenance domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.models import ProvenanceLinkRecord, SourceAnchorRecord
from src.dataservice.domains.provenance.service import ProvenanceDataDomainService
from src.dataservice.domains.source.contracts import (
    SourceBibliographyCreateCommand,
    SourceCitationUsageCreateCommand,
    SourceCreateCommand,
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
        return []

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
