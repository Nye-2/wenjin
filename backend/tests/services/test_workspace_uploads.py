"""Tests for workspace upload helpers."""

from pathlib import Path

import pytest

from src.services.workspace_uploads import (
    extract_document_preview,
    resolve_workspace_upload_stored_path,
    workspace_upload_public_url,
)


def test_extract_document_preview_reads_text_files():
    preview = extract_document_preview(
        "notes.md",
        "text/markdown",
        content=b"# Heading\n\nThis is a sample upload.\n",
    )

    assert preview["title"] is None
    assert preview["authors"] == []
    assert preview["page_count"] is None
    assert preview["text_preview"] == "# Heading This is a sample upload."


def test_workspace_upload_public_url_accepts_root_prefixed_relative_path(tmp_path: Path):
    root = tmp_path / "workspace_uploads"
    expected_path = (root / "ws-1" / "references" / "_preprocessed" / "paper" / "doc_0.md").resolve()

    url = workspace_upload_public_url(
        "ws-1",
        "/references/_preprocessed/paper/doc_0.md",
        root=root,
    )

    assert url == "/api/workspaces/ws-1/files/references/_preprocessed/paper/doc_0.md"
    resolved = resolve_workspace_upload_stored_path(
        "ws-1",
        "/references/_preprocessed/paper/doc_0.md",
        root=root,
        allow_root_prefixed_relative=True,
    )
    assert resolved == expected_path


def test_resolve_workspace_upload_stored_path_rejects_root_prefixed_relative_by_default(
    tmp_path: Path,
):
    root = tmp_path / "workspace_uploads"
    with pytest.raises(ValueError, match="escapes workspace uploads root"):
        resolve_workspace_upload_stored_path(
            "ws-1",
            "/references/_preprocessed/paper/doc_0.md",
            root=root,
        )
