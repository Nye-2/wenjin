"""Workflow gate for Reference Library evidence-to-writing contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dataservice.source_api import (
    SourceCitationUsageCreateCommand,
    SourceDataService,
    SourceEvidencePackCreateCommand,
)
from src.dataservice_client.contracts.source import (
    ReferenceEvidenceLevel,
    ReferenceLibraryStatus,
)
from src.services.references import SourceBibliographyService


def _execute_result(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar_one_or_none(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _reference(
    *,
    reference_id: str,
    title: str,
    citation_key: str,
    library_status: ReferenceLibraryStatus | str = ReferenceLibraryStatus.INCLUDED,
    evidence_level: ReferenceEvidenceLevel | str = ReferenceEvidenceLevel.INDEXED_FULLTEXT,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=reference_id,
        workspace_id="ws-1",
        source_kind="paper",
        title=title,
        normalized_title=title.lower(),
        authors=["Ada Lovelace"],
        authors_json=["Ada Lovelace"],
        year=2026,
        venue="Journal of Workflow Gates",
        publication_type="article",
        doi=None,
        url=None,
        abstract="Evidence summary",
        citation_count=7,
        source_type="paper",
        ingest_kind="web_search",
        source_label="Model-native web search",
        ingest_label="Model-native web search",
        ingest_mission_id=None,
        ingest_mission_commit_id=None,
        verified_at=None,
        library_status=library_status,
        evidence_level=evidence_level,
        fulltext_status="indexed",
        citation_key=citation_key,
        bibtex_entry_type="article",
        bibtex_fields={},
        bibtex_fields_json={},
        read_status="read",
        tags=[],
        tags_json=[],
        notes=None,
        is_deleted=False,
        created_at=None,
        updated_at=None,
    )


class _BibliographyDataService:
    def __init__(self, references: list[SimpleNamespace], workspace: SimpleNamespace | None = None) -> None:
        self.references = references
        self.workspace = workspace
        self.snapshot: object | None = None

    async def list_sources(
        self,
        *,
        library_status: str | None = None,
        include_excluded: bool = True,
        **_kwargs: object,
    ) -> list[SimpleNamespace]:
        rows = self.references
        if library_status is not None:
            rows = [
                row
                for row in rows
                if str(getattr(row.library_status, "value", row.library_status)) == library_status
            ]
        if not include_excluded:
            rows = [
                row
                for row in rows
                if str(getattr(row.library_status, "value", row.library_status)) != ReferenceLibraryStatus.EXCLUDED.value
            ]
        return rows

    async def build_source_bibliography(self, command: object) -> SimpleNamespace:
        source_ids = set(getattr(command, "source_ids", []))
        rows = [row for row in self.references if row.id in source_ids]
        content = "\n".join(
            f"@article{{{row.citation_key},\n  title={{{row.title}}}\n}}"
            for row in rows
        )
        return SimpleNamespace(
            content=content,
            count=len(rows),
            source_ids=[row.id for row in rows],
            citation_keys=[row.citation_key for row in rows],
        )

    async def get_workspace(self, _workspace_id: str) -> SimpleNamespace | None:
        return self.workspace

    async def create_source_bibliography_snapshot(self, command: object) -> SimpleNamespace:
        self.snapshot = command
        return SimpleNamespace(id="snapshot-1")


@pytest.mark.asyncio
async def test_reference_evidence_usage_bibtex_prism_validation_workflow_gate() -> None:
    """Keep the writing workflow bounded by Reference Library SSOT contracts."""
    reference = _reference(
        reference_id="ref-1",
        title="Grounded Evidence",
        citation_key="lovelace2026",
    )
    excluded_reference = _reference(
        reference_id="ref-excluded",
        title="Excluded Evidence",
        citation_key="excluded2026",
        library_status=ReferenceLibraryStatus.EXCLUDED,
    )
    workspace = SimpleNamespace(id="ws-1", name="Workflow Workspace")
    latex_project = SimpleNamespace(id="latex-1", main_file="main.tex")

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _execute_result([reference]),
            _execute_result([]),
            _execute_result([]),
            _execute_result([reference]),
            _execute_result([reference, excluded_reference]),
            _execute_result([reference]),
            _execute_result([reference]),
            _scalar_one_or_none(workspace),
        ]
    )
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    evidence_pack = await SourceDataService(db, autocommit=False).build_evidence_pack(
        SourceEvidencePackCreateCommand(
            workspace_id="ws-1",
            query="grounded",
            max_units=4,
        )
    )

    assert evidence_pack.policy == "outline_first_no_vector_rag"
    assert evidence_pack.library_outline[0]["reference"]["citation_key"] == "lovelace2026"
    assert evidence_pack.selected_units == []

    usage_result = await SourceDataService(db).record_citation_usage(
        SourceCitationUsageCreateCommand(
            workspace_id="ws-1",
            citation_keys=["lovelace2026"],
            latex_project_id="latex-1",
            target_id="latex-1",
            target_section="Introduction",
            generated_text=r"Grounded claim \cite{lovelace2026}.",
        )
    )

    assert usage_result.recorded == 1
    assert usage_result.source_ids == ["ref-1"]
    assert usage_result.citation_keys == ["lovelace2026"]
    assert reference.library_status == "used_in_draft"
    usage_link = db.add.call_args.args[0]
    assert usage_link.citation_key == "lovelace2026"
    assert usage_link.target_domain == "prism"
    assert usage_link.target_kind == "prism_file"
    assert usage_link.target_id == "latex-1"
    assert usage_link.target_ref_json["latex_project_id"] == "latex-1"
    assert usage_link.target_ref_json["target_section"] == "Introduction"

    bibliography_data = _BibliographyDataService([reference, excluded_reference], workspace)
    validation = await SourceBibliographyService(bibliography_data).validate_citations(
        workspace_id="ws-1",
        latex_content=r"Grounded claim \cite{lovelace2026}.",
    )

    assert validation["valid"] is True
    assert validation["missing_keys"] == []
    assert validation["unverified_keys"] == []
    assert "excluded2026" in validation["unused_bib_keys"]

    project_service = MagicMock()
    project_service.write_text_file = AsyncMock()
    project_service.read_text_file.return_value = "\\begin{document}\nBody\n\\end{document}\n"
    workspace_latex_service = MagicMock()
    workspace_latex_service.ensure_workspace_project = AsyncMock(return_value=latex_project)

    with (
        patch(
            "src.services.references.service.WorkspaceLatexProjectService",
            return_value=workspace_latex_service,
        ),
        patch(
            "src.services.references.service.LatexProjectService",
            return_value=project_service,
        ),
    ):
        sync_result = await SourceBibliographyService(bibliography_data).sync_prism(
            workspace_id="ws-1",
            scope="used_only",
        )

    assert sync_result["latex_project_id"] == "latex-1"
    assert sync_result["synced_file"] == "refs.bib"
    assert sync_result["reference_count"] == 1
    assert "@article{lovelace2026" in sync_result["content"]
    assert "excluded2026" not in sync_result["content"]
    project_service.write_text_file.assert_any_await(
        latex_project,
        "refs.bib",
        sync_result["content"],
    )
    assert project_service.write_text_file.await_args_list[-1].args[1] == "main.tex"
    assert "\\bibliography{refs}" in project_service.write_text_file.await_args_list[-1].args[2]
    snapshot = bibliography_data.snapshot
    assert snapshot is not None
    assert snapshot.workspace_id == "ws-1"
    assert snapshot.prism_project_id == "latex-1"
    assert snapshot.scope == "used_only"


@pytest.mark.asyncio
async def test_reference_citation_validation_blocks_missing_and_metadata_only_keys() -> None:
    verified_reference = _reference(
        reference_id="ref-1",
        title="Verified Evidence",
        citation_key="verified2026",
        evidence_level=ReferenceEvidenceLevel.EXTERNAL_VERIFIED,
    )
    metadata_only_reference = _reference(
        reference_id="ref-2",
        title="Metadata Only",
        citation_key="metadata2026",
        evidence_level=ReferenceEvidenceLevel.METADATA_ONLY,
    )
    validation = await SourceBibliographyService(
        _BibliographyDataService([verified_reference, metadata_only_reference])
    ).validate_citations(
        workspace_id="ws-1",
        latex_content=r"\cite{verified2026, metadata2026, missing2026}",
    )

    assert validation["valid"] is False
    assert validation["missing_keys"] == ["missing2026"]
    assert validation["unverified_keys"] == ["metadata2026"]
