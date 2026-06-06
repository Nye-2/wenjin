"""Generated artifact discovery for workspace sandbox jobs."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from collections.abc import Iterable
from typing import Any

from src.sandbox.workspace_layout import (
    WORKSPACE_ARTIFACT_ROOTS,
    is_workspace_internal_path,
    normalize_workspace_virtual_path,
)

DISCOVERY_SCHEMA = "wenjin.sandbox.generated_artifact_candidate.v1"
DISCOVERY_ROOTS: tuple[tuple[str, str, str], ...] = tuple(
    (root["virtual_path"], root["name"], root["artifact_kind"])
    for root in WORKSPACE_ARTIFACT_ROOTS
)

logger = logging.getLogger(__name__)


async def discover_generated_artifacts(
    sandbox: Any,
    *,
    roots: Iterable[tuple[str, str, str]] = DISCOVERY_ROOTS,
    max_depth: int = 3,
    max_items: int = 50,
    hash_max_bytes: int = 2_000_000,
) -> list[dict[str, Any]]:
    """Return user-reviewable artifact candidates produced inside the sandbox.

    This is an in-lease discovery contract only. DataService materialization
    happens later, after a user-facing review path decides which candidates
    should become canonical `sandbox_artifact` records.
    """

    candidates: dict[str, dict[str, Any]] = {}
    for root, root_name, artifact_kind in roots:
        try:
            entries = await sandbox.list_dir(root, max_depth=max_depth)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except Exception as exc:  # pragma: no cover - exact provider failures vary.
            logger.warning("Skipping sandbox artifact discovery root %s: %s", root, exc)
            continue
        for entry in entries:
            path = _normalize_virtual_path(getattr(entry, "path", ""))
            if not path or getattr(entry, "is_dir", False) or is_workspace_internal_path(path):
                continue
            size = _coerce_size(getattr(entry, "size", None))
            candidates[path] = {
                "schema": DISCOVERY_SCHEMA,
                "path": path,
                "root": root_name,
                "artifact_kind": artifact_kind,
                "mime_type": _guess_mime_type(path),
                "size": size,
                "content_hash": await _content_hash(
                    sandbox=sandbox,
                    path=path,
                    size=size,
                    hash_max_bytes=hash_max_bytes,
                ),
                "review_surface": "sandbox_artifact",
                "materialization_status": "candidate",
            }
            if len(candidates) >= max_items:
                return [candidates[key] for key in sorted(candidates)]
    return [candidates[key] for key in sorted(candidates)]


def summarize_generated_artifacts(artifacts: list[dict[str, Any]]) -> str:
    """Render a compact report section for generated artifact candidates."""

    if not artifacts:
        return ""
    lines = ["\n\n## Generated artifacts\n"]
    for artifact in artifacts:
        size = artifact.get("size")
        size_text = f" ({size} bytes)" if size is not None else ""
        lines.append(
            f"- `{artifact['path']}` - {artifact['artifact_kind']}, "
            f"{artifact.get('mime_type') or 'application/octet-stream'}{size_text}"
        )
    return "\n".join(lines) + "\n"


def _normalize_virtual_path(path: str) -> str:
    try:
        return normalize_workspace_virtual_path(path)
    except ValueError:
        return ""


def _coerce_size(value: Any) -> int | None:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return max(size, 0)


def _guess_mime_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


async def _content_hash(
    *,
    sandbox: Any,
    path: str,
    size: int | None,
    hash_max_bytes: int,
) -> str | None:
    if size is not None and size > hash_max_bytes:
        return None
    try:
        content = await sandbox.read_file(path)
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None
    encoded = str(content).encode("utf-8")
    if len(encoded) > hash_max_bytes:
        return None
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
