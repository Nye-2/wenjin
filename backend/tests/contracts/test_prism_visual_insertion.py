"""Shared Prism insertion contract tests."""

from __future__ import annotations

import pytest

from src.contracts.prism_context import prism_selection_hash
from src.contracts.prism_visual_insertion import insert_after_prism_selection


def test_insert_after_selection_preserves_crlf_without_storing_full_document() -> None:
    content = "alpha\r\nselected\r\nomega\r\n"
    selection = "selected"
    start = len(b"alpha\r\n")
    end = start + len(selection)

    result = insert_after_prism_selection(
        content=content,
        selection_byte_range=(start, end),
        selection_hash=prism_selection_hash(selection),
        insertion="![Figure](/figure.png)",
    )

    assert result == (
        "alpha\r\nselected\r\n\r\n"
        "![Figure](/figure.png)\r\n\r\n"
        "omega\r\n"
    )


def test_insert_after_selection_rejects_stale_selection_hash() -> None:
    with pytest.raises(ValueError, match="selection changed"):
        insert_after_prism_selection(
            content="selected",
            selection_byte_range=(0, 8),
            selection_hash=prism_selection_hash("different"),
            insertion="![Figure](/figure.png)",
        )
