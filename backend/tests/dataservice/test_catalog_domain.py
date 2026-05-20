"""DataService catalog domain tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.catalog.seed_loader import DataServiceCatalogSeedLoader
from src.dataservice.domains.catalog.service import DataServiceCatalogService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


class FakeCatalogRepository:
    def __init__(self) -> None:
        self.capability_values: dict[str, Any] | None = None
        self.skill_values: dict[str, Any] | None = None
        self.latest = None

    async def upsert_capability(self, values: dict[str, Any]):
        self.capability_values = values
        return SimpleNamespace(created_at=None, updated_at=None, **values)

    async def upsert_skill(self, values: dict[str, Any]):
        self.skill_values = values
        return SimpleNamespace(**values)

    async def latest_seed_revision(self, *, catalog_kind: str, seed_root: str):
        return self.latest

    def create_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
        loaded_count: int,
        metadata_json: dict[str, Any],
    ):
        self.latest = SimpleNamespace(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
            loaded_count=loaded_count,
            metadata_json=metadata_json,
        )
        return self.latest


def _service() -> tuple[DataServiceCatalogService, FakeCatalogRepository, FakeSession]:
    session = FakeSession()
    service = DataServiceCatalogService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeCatalogRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


@pytest.mark.asyncio
async def test_upsert_capability_materializes_v2_definition_json() -> None:
    service, repository, session = _service()

    record = await service.upsert_capability(
        {
            "id": "idea_to_thesis_manuscript",
            "workspace_type": "thesis",
            "display_name": "从想法到全文",
            "intent_description": "根据确定的 idea 完成全文写作",
            "brief_schema": {"type": "object"},
            "graph_template": {"phases": []},
            "ui_meta": {"order": 1},
        },
        checksum="abc",
        source_path="seed.yaml",
    )

    assert record.schema_version == "capability.v2"
    assert record.tier == "primary"
    assert record.entry_surface == "workbench"
    assert record.definition_json["schema_version"] == "capability.v2"
    assert record.checksum == "abc"
    assert repository.capability_values is not None
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upsert_skill_materializes_worker_type_and_skill_json() -> None:
    service, repository, session = _service()

    record = await service.upsert_skill(
        {
            "id": "manuscript-writer",
            "display_name": "全文写手",
            "subagent_type": "react",
            "prompt": "write",
            "config": {"output_kind": "document"},
        }
    )

    assert record.schema_version == "capability_skill.v2"
    assert record.worker_type == "react"
    assert record.skill_json["worker_type"] == "react"
    assert repository.skill_values is not None
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_seed_revision_is_idempotent_by_checksum() -> None:
    service, repository, session = _service()

    first = await service.record_seed_revision(
        catalog_kind="capabilities",
        seed_root="/seed/capabilities",
        checksum="same",
        loaded_count=2,
    )
    second = await service.record_seed_revision(
        catalog_kind="capabilities",
        seed_root="/seed/capabilities",
        checksum="same",
        loaded_count=2,
    )

    assert first.loaded == 2
    assert first.skipped is False
    assert second.loaded == 0
    assert second.skipped is True
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_seed_loader_applies_capability_revision_once(tmp_path) -> None:
    service, repository, session = _service()
    seed_dir = tmp_path / "capabilities"
    workspace_dir = seed_dir / "thesis"
    workspace_dir.mkdir(parents=True)
    seed_file = workspace_dir / "idea_to_thesis.yaml"
    seed_file.write_text("id: idea_to_thesis_manuscript\n", encoding="utf-8")

    def validate(path, text):
        assert path == seed_file
        assert "idea_to_thesis_manuscript" in text
        return {
            "id": "idea_to_thesis_manuscript",
            "workspace_type": "thesis",
            "display_name": "从想法到全文",
            "intent_description": "根据确定的 idea 完成全文写作",
            "brief_schema": {"type": "object"},
            "graph_template": {"phases": []},
            "ui_meta": {},
        }

    result = await DataServiceCatalogSeedLoader(service, seed_dir).load_capabilities(
        validate_yaml_text=validate,
    )

    assert result.loaded == 1
    assert result.skipped is False
    assert result.checksum
    assert repository.capability_values is not None
    assert repository.capability_values["source_path"] == str(seed_file)
    assert repository.latest.metadata_json["schema_version"] == "capability.v2"
    assert session.commit_count == 1
