"""Reference Library import service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.references.service import SourceLibraryImportService


def test_artifact_reference_candidates_ignore_unverified_reference_suggestions() -> None:
    content = {
        "verified_papers": [
            {"title": "Verified", "external_id": "ss-1", "source": "semantic_scholar"}
        ],
        "semantic_scholar_results": [
            {"title": "Also verified", "external_id": "ss-2", "source": "semantic_scholar"}
        ],
        "references": [
            {"title": "LLM suggestion without source"}
        ],
    }

    candidates = SourceLibraryImportService._iter_artifact_reference_candidates(content)

    assert [item["title"] for item in candidates] == ["Verified", "Also verified"]


@pytest.mark.asyncio
async def test_large_uploaded_pdf_commits_asset_before_scheduling_preprocess(tmp_path) -> None:
    events: list[str] = []
    db = AsyncMock()

    async def _commit() -> None:
        events.append("commit")

    db.commit.side_effect = _commit
    db.refresh = AsyncMock()
    source = SimpleNamespace(
        id="source-1",
        workspace_id="ws-1",
        title="Uploaded",
        normalized_title="uploaded",
        authors_json=[],
        year=None,
        venue=None,
        publication_type=None,
        doi=None,
        url=None,
        abstract=None,
        citation_count=None,
        ingest_kind="upload",
        ingest_label="PDF upload",
        ingest_execution_id=None,
        verified_at=None,
        library_status="included",
        evidence_level="uploaded_fulltext",
        fulltext_status="uploaded",
        citation_key="uploaded",
        bibtex_entry_type="article",
        bibtex_fields_json={},
        read_status="unread",
        tags_json=[],
        notes=None,
        is_deleted=False,
        created_at=None,
        updated_at=None,
    )
    workspace_asset = SimpleNamespace(id="workspace-asset-1")

    class _SourceService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def import_source(self, _command):
            return SimpleNamespace(source=source, created=True)

        async def link_source_asset(self, **_kwargs):
            return {
                "id": "source-asset-1",
                "source_id": "source-1",
                "workspace_asset_id": "workspace-asset-1",
                "asset_type": "pdf",
                "preprocess_status": "pending",
            }

        async def update_source(self, **_kwargs):
            return source

        async def update_source_asset(self, **_kwargs):
            return {
                "id": "source-asset-1",
                "source_id": "source-1",
                "workspace_asset_id": "workspace-asset-1",
                "asset_type": "pdf",
                "preprocess_status": "pending",
            }

        async def get_source_for_workspace(self, **_kwargs):
            return source

    class _AssetService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def register_asset_record(self, **_kwargs):
            return workspace_asset

    task_service = AsyncMock()

    async def _submit_task(**kwargs):
        events.append("submit")
        return "task-1"

    task_service.submit_task.side_effect = _submit_task
    service = SourceLibraryImportService(db)

    with (
        patch("src.services.references.service.workspace_upload_dir", return_value=tmp_path),
        patch("src.services.references.service.workspace_upload_public_url", return_value="/file.pdf"),
        patch("src.services.references.service.SourceDataService", _SourceService),
        patch("src.services.references.service.AssetDataService", _AssetService),
        patch("src.services.references.service.REFERENCE_PREPROCESS_THRESHOLD_BYTES", 1),
    ):
        result = await service.import_uploaded_pdf(
            workspace_id="ws-1",
            filename="paper.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 content",
            task_service=task_service,
            user_id="user-1",
            thread_id="thread-1",
        )

    assert events[:2] == ["commit", "submit"]
    assert result["preprocess"]["task_id"] == "task-1"
    payload = task_service.submit_task.await_args.kwargs["payload"]
    assert payload["source_id"] == "source-1"
    assert payload["source_asset_id"] == "source-asset-1"
    assert payload["workspace_asset_id"] == "workspace-asset-1"
    assert payload["thread_id"] == "thread-1"
