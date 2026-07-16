"""Canonical identities for immutable, unmaterialized text candidates."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def artifact_candidate_content_hash(preview_text: str) -> str:
    return "sha256:" + hashlib.sha256(preview_text.encode("utf-8")).hexdigest()


def artifact_candidate_ref(metadata: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"artifact-candidate:{digest}"


def valid_artifact_candidate_receipt(
    candidate_ref: str,
    metadata: dict[str, Any],
) -> bool:
    preview_text = metadata.get("preview_text")
    return (
        metadata.get("materialized") is False
        and isinstance(preview_text, str)
        and bool(preview_text.strip())
        and str(metadata.get("mime_type") or "") == "text/markdown"
        and str(metadata.get("content_hash") or "")
        == artifact_candidate_content_hash(preview_text)
        and candidate_ref == artifact_candidate_ref(metadata)
    )


__all__ = [
    "artifact_candidate_content_hash",
    "artifact_candidate_ref",
    "valid_artifact_candidate_receipt",
]
