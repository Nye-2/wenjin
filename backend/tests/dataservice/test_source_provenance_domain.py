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
from src.dataservice.domains.source.contracts import SourceCreateCommand
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
        source_id = f"source-{len(self.sources) + 1}"
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

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.sources.values() if record.workspace_id == workspace_id]
        if library_status is not None:
            records = [record for record in records if record.library_status == library_status]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        return records[:limit]


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
