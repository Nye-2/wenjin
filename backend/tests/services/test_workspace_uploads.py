"""Tests for workspace upload helpers."""

from src.services.workspace_uploads import extract_document_preview


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
