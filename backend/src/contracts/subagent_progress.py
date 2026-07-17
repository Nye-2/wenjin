"""Canonical identity for durable subagent progress MissionItems."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def subagent_progress_sha256(
    *,
    summary: str | None,
    payload_json: Mapping[str, Any],
) -> str:
    canonical_payload = dict(payload_json)
    canonical_payload.pop("progress_id", None)
    canonical_payload.pop("progress_sha256", None)
    encoded = json.dumps(
        {
            "summary": summary or "",
            "payload_json": canonical_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_subagent_progress_identity(
    *,
    summary: str | None,
    payload_json: Mapping[str, Any],
) -> tuple[str, str]:
    progress_id = payload_json.get("progress_id")
    claimed_hash = payload_json.get("progress_sha256")
    job_id = payload_json.get("job_id")
    lifecycle_phase = payload_json.get("lifecycle_phase")
    if (
        not isinstance(progress_id, str)
        or not progress_id
        or not isinstance(claimed_hash, str)
        or _SHA256_RE.fullmatch(claimed_hash) is None
        or not isinstance(job_id, str)
        or not job_id
        or not isinstance(lifecycle_phase, str)
        or not lifecycle_phase
    ):
        raise ValueError(
            "subagent progress requires identity, hash, job, and lifecycle phase"
        )
    actual_hash = subagent_progress_sha256(
        summary=summary,
        payload_json=payload_json,
    )
    expected_id = (
        f"subagent-terminal:{job_id}"
        if lifecycle_phase == "terminal"
        else f"subagent-progress:{actual_hash}"
    )
    if claimed_hash != actual_hash or progress_id != expected_id:
        raise ValueError("subagent progress identity or hash is invalid")
    return progress_id, actual_hash


__all__ = [
    "subagent_progress_sha256",
    "validate_subagent_progress_identity",
]
