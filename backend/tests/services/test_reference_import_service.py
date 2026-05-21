"""Reference Library import service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.references.service import ReferenceImportService


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

    candidates = ReferenceImportService._iter_artifact_reference_candidates(content)

    assert [item["title"] for item in candidates] == ["Verified", "Also verified"]


@pytest.mark.asyncio
async def test_large_uploaded_pdf_commits_asset_before_scheduling_preprocess(tmp_path) -> None:
    events: list[str] = []
    db = AsyncMock()

    async def _commit() -> None:
        events.append("commit")

    db.commit.side_effect = _commit
    db.refresh = AsyncMock()
    reference = SimpleNamespace(
        id="reference-1",
        workspace_id="ws-1",
        title="Uploaded",
        fulltext_status="uploaded",
    )
    task_service = AsyncMock()

    async def _submit_task(**kwargs):
        events.append("submit")
        return "task-1"

    task_service.submit_task.side_effect = _submit_task
    service = ReferenceImportService(db)
    service.references = SimpleNamespace(
        upsert_reference=AsyncMock(return_value=(reference, True))
    )

    with (
        patch("src.services.references.service.workspace_upload_dir", return_value=tmp_path),
        patch("src.services.references.service.workspace_upload_public_url", return_value="/file.pdf"),
        patch("src.services.references.service.serialize_reference", return_value={"id": "reference-1"}),
        patch("src.services.references.service.serialize_asset", return_value={"id": "asset-1"}),
        patch("src.services.references.service._sync_reference_assets_to_dataservice", new_callable=AsyncMock),
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
    assert payload["reference_id"] == "reference-1"
    assert payload["thread_id"] == "thread-1"
