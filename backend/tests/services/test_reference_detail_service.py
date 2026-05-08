"""Reference detail service tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.references import WorkspaceReferenceService

NOW = datetime(2026, 5, 6, tzinfo=UTC)


def _scalar_one_or_none(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _reference() -> SimpleNamespace:
    return SimpleNamespace(
        id="ref-1",
        workspace_id="ws-1",
        title="Reference Title",
        normalized_title="reference title",
        authors=["Ada Lovelace"],
        year=2026,
        venue="Journal",
        publication_type="article",
        doi="10.1000/example",
        url="https://example.test/paper",
        abstract="Abstract",
        citation_count=12,
        source_type="semantic_scholar",
        source_label="Semantic Scholar",
        source_run_id="run-1",
        source_artifact_id="artifact-1",
        verified_at=NOW,
        library_status="included",
        evidence_level="indexed_fulltext",
        fulltext_status="indexed",
        citation_key="lovelace2026",
        bibtex_entry_type="article",
        bibtex_fields={},
        read_status="unread",
        tags=[],
        notes=None,
        is_deleted=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _asset() -> SimpleNamespace:
    return SimpleNamespace(
        id="asset-1",
        workspace_id="ws-1",
        reference_id="ref-1",
        source_asset_id=None,
        asset_type="pdf",
        file_path="references/paper.pdf",
        virtual_path=None,
        public_url="/api/workspaces/ws-1/files/references/paper.pdf",
        content_type="application/pdf",
        file_size=1024,
        file_hash="hash",
        page_count=8,
        language="en",
        preprocess_status="succeeded",
        preprocess_task_id="task-1",
        preprocess_error=None,
        manifest_path="references/_preprocessed/paper/manifest.json",
        markdown_paths=["references/_preprocessed/paper/doc_0.md"],
        created_at=NOW,
        updated_at=NOW,
    )


def _external_id() -> SimpleNamespace:
    return SimpleNamespace(
        id="external-1",
        workspace_id="ws-1",
        reference_id="ref-1",
        source="semantic_scholar",
        external_id="S2-123",
        url="https://semanticscholar.org/paper/S2-123",
        created_at=NOW,
        updated_at=NOW,
    )


def _usage_event() -> SimpleNamespace:
    return SimpleNamespace(
        id="usage-1",
        workspace_id="ws-1",
        reference_id="ref-1",
        outline_node_id="node-1",
        text_unit_id="unit-1",
        execution_session_id="exec-1",
        task_id="task-2",
        artifact_id="artifact-2",
        latex_project_id="latex-1",
        target_section="Introduction",
        claim_text="A supported claim",
        generated_text="Generated draft",
        citation_key="lovelace2026",
        usage_type="citation_only",
        accepted_status="pending",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_get_reference_detail_includes_preprocess_source_and_usage() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_one_or_none(_reference()),
            _scalars([_asset()]),
            _scalars([_external_id()]),
            _scalars([_usage_event()]),
        ]
    )

    detail = await WorkspaceReferenceService(db).get_reference_detail(
        "ws-1",
        "ref-1",
    )

    assert detail is not None
    assert detail["reference"]["assets"][0]["preprocess_status"] == "succeeded"
    assert detail["preprocess"]["status"] == "succeeded"
    assert detail["preprocess"]["task_ids"] == ["task-1"]
    assert detail["external_ids"][0]["external_id"] == "S2-123"
    assert detail["source_history"][0]["source_type"] == "semantic_scholar"
    assert detail["usage_events"][0]["artifact_id"] == "artifact-2"
    assert detail["usage_summary"]["recent_count"] == 1
    assert detail["usage_summary"]["status_counts"] == {"pending": 1}


@pytest.mark.asyncio
async def test_get_reference_detail_returns_none_for_missing_reference() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none(None))

    detail = await WorkspaceReferenceService(db).get_reference_detail(
        "ws-1",
        "missing",
    )

    assert detail is None
