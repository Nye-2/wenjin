"""Canonical identities for immutable, unmaterialized text candidates."""

from __future__ import annotations

import hashlib
import json
import re
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
    common = (
        metadata.get("materialized") is False
        and isinstance(preview_text, str)
        and bool(preview_text.strip())
        and candidate_ref == artifact_candidate_ref(metadata)
    )
    if not common:
        return False
    mime_type = str(metadata.get("mime_type") or "")
    if mime_type == "text/markdown":
        return str(metadata.get("content_hash") or "") == artifact_candidate_content_hash(preview_text)
    sandbox_ref = str(metadata.get("sandbox_artifact_ref") or "")
    source_refs = metadata.get("source_refs")
    return (
        mime_type in {
            "text/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/zip",
        }
        and isinstance(source_refs, list)
        and sandbox_ref in source_refs
        and sandbox_ref.startswith("sandbox-artifact:")
        and isinstance(metadata.get("filename"), str)
        and bool(str(metadata.get("filename") or "").strip())
        and isinstance(metadata.get("preview_ref"), str)
        and bool(str(metadata.get("preview_ref") or ""))
        and isinstance(metadata.get("preview_expires_at"), str)
        and bool(str(metadata.get("preview_expires_at") or ""))
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("content_hash") or "")))
        and isinstance(metadata.get("size_bytes"), int)
        and int(metadata.get("size_bytes") or 0) > 0
    )


__all__ = [
    "artifact_candidate_content_hash",
    "artifact_candidate_ref",
    "valid_artifact_candidate_receipt",
]
