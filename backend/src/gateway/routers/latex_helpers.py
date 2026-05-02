"""LaTeX router helper functions."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import logging
import os
import zipfile
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import WorkspaceReference
from src.gateway.contracts.latex import (
    _MAX_REWRITE_CANDIDATES,
    _REWRITE_CANDIDATE_TIMEOUT_SECONDS,
    _REWRITE_PROFILE_GUIDANCE,
    _REWRITE_PROFILE_ORDER,
    LatexDiffPayload,
    LatexFeedbackAnchorPayload,
    LatexFeedbackRewriteCandidatePayload,
    LatexFeedbackRewriteRequest,
    LatexFileChangePreviewResponse,
    RewriteProfile,
    RewriteRiskLevel,
)
from src.services.latex import LatexProjectService
from src.services.latex.feedback_revision_service import (
    build_feedback_anchor,
    rewrite_with_feedback,
)
from src.services.latex.paths import is_reserved_project_path, normalize_relative_path
from src.services.latex.rewrite_diff import (
    build_latex_rewrite_diff,
    compute_content_hash,
    compute_range_hash,
)
from src.services.latex.rewrite_guard import (
    LatexStructureValidationError,
    validate_rewrite_segment,
)
from src.services.references import ReferenceUsageService
from src.services.references.utils import extract_citation_keys_from_text

logger = logging.getLogger(__name__)

_MAX_UPLOAD_ARCHIVE_FILES = 5000
_MAX_UPLOAD_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_UPLOAD_READ_CHUNK_SIZE = 64 * 1024


def _normalize_upload_relative_path(filename: str | None, base_path: str | None) -> str:
    """Normalize upload filename against optional base path without double-prefixing."""
    normalized_name = str(filename or "").replace("\\", "/").strip().lstrip("/")
    if not normalized_name:
        return ""
    normalized_base = str(base_path or "").replace("\\", "/").strip().strip("/")
    if not normalized_base:
        return normalize_relative_path(normalized_name)
    if (
        normalized_name == normalized_base
        or normalized_name.startswith(f"{normalized_base}/")
    ):
        merged = normalized_name
    else:
        merged = f"{normalized_base}/{normalized_name}"
    return normalize_relative_path(merged)


def _is_reserved_upload_path(relative_path: str) -> bool:
    return is_reserved_project_path(relative_path)


def _sorted_folder_paths(paths: set[str]) -> list[str]:
    return sorted(paths, key=lambda item: (item.count("/"), item))


async def _read_upload_bytes_with_limit(
    upload: UploadFile,
    *,
    max_size_bytes: int,
    chunk_size: int = _UPLOAD_READ_CHUNK_SIZE,
    error_label: str = "Archive file",
) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"{error_label} too large. Maximum size is "
                    f"{max_size_bytes // (1024 * 1024)}MB"
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _common_upload_root_prefix(paths: list[str]) -> str | None:
    cleaned = [path for path in paths if path]
    if not cleaned:
        return None
    first_parts = cleaned[0].split("/")
    if len(first_parts) < 2:
        return None
    root = first_parts[0]
    for current in cleaned:
        parts = current.split("/")
        if not parts or parts[0] != root:
            return None
    return root


def _collect_archive_upload_payload(
    archive_bytes: bytes,
    *,
    base_path: str | None,
    strip_root: bool = True,
) -> tuple[list[tuple[str, bytes]], list[str], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid ZIP archive") from exc

    parsed_entries: list[tuple[str, bool, bytes | None]] = []

    with archive:
        entries = archive.infolist()
        if len(entries) > _MAX_UPLOAD_ARCHIVE_FILES:
            raise ValueError("Archive contains too many files")

        total_uncompressed_bytes = 0
        for entry in entries:
            total_uncompressed_bytes += max(0, int(entry.file_size or 0))
            if total_uncompressed_bytes > _MAX_UPLOAD_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError("Archive is too large after extraction")

            try:
                normalized = _normalize_upload_relative_path(entry.filename, None)
            except ValueError as exc:
                raise ValueError(f"Invalid archive path: {entry.filename}") from exc

            if not normalized:
                continue
            parsed_entries.append(
                (
                    normalized,
                    entry.is_dir(),
                    None if entry.is_dir() else archive.read(entry),
                )
            )

    if strip_root:
        root_prefix = _common_upload_root_prefix([path for path, _, _ in parsed_entries])
        if root_prefix:
            prefix = f"{root_prefix}/"
            adjusted_entries: list[tuple[str, bool, bytes | None]] = []
            for path, is_dir, payload in parsed_entries:
                if path == root_prefix:
                    continue
                if path.startswith(prefix):
                    next_path = path[len(prefix):]
                else:
                    next_path = path
                if not next_path:
                    continue
                adjusted_entries.append((next_path, is_dir, payload))
            parsed_entries = adjusted_entries

    files: dict[str, bytes] = {}
    folders: set[str] = set()
    skipped: list[str] = []
    for path, is_dir, payload in parsed_entries:
        try:
            final_path = _normalize_upload_relative_path(path, base_path)
        except ValueError as exc:
            raise ValueError(f"Invalid archive path: {path}") from exc

        if _is_reserved_upload_path(final_path):
            skipped.append(final_path)
            continue
        if is_dir:
            folders.add(final_path)
            continue
        files[final_path] = payload or b""
        parent = Path(final_path).parent.as_posix()
        if parent not in {"", "."}:
            folders.add(parent)

    return list(files.items()), _sorted_folder_paths(folders), list(dict.fromkeys(skipped))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _read_feedback_items_from_project(project_llm_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    llm_config = deepcopy(project_llm_config) if isinstance(project_llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    if not isinstance(metadata, dict):
        return []
    items = metadata.get("feedback_items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


async def _write_feedback_items_to_project(
    *,
    service: LatexProjectService,
    project: Any,
    items: list[dict[str, Any]],
) -> None:
    llm_config = deepcopy(project.llm_config) if isinstance(project.llm_config, dict) else {}
    metadata = deepcopy(llm_config.get("metadata")) if isinstance(llm_config.get("metadata"), dict) else {}
    metadata["feedback_items"] = items
    metadata["feedback_updated_at"] = datetime.now().isoformat()
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)


@lru_cache(maxsize=1)
def _rewrite_signature_secret() -> bytes:
    raw = str(os.getenv("WENJIN_LATEX_REWRITE_SIGNING_KEY", "")).strip()
    if not raw:
        raw = "wenjin-latex-rewrite-signing-key"
    return raw.encode("utf-8")


def _compute_candidate_signature(
    *,
    file_path: str,
    candidate_id: str,
    target_start: int,
    target_end: int,
    rewritten_text: str,
    base_file_hash: str,
    base_range_hash: str,
) -> str:
    payload = "\x1f".join(
        [
            str(file_path),
            str(candidate_id),
            str(target_start),
            str(target_end),
            str(base_file_hash),
            str(base_range_hash),
            str(rewritten_text),
        ]
    )
    return hmac.new(
        _rewrite_signature_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _compute_revert_signature(
    *,
    file_path: str,
    candidate_id: str,
    revert_start: int,
    revert_end: int,
    rewritten_text: str,
    previous_text: str,
    applied_file_hash: str,
) -> str:
    payload = "\x1f".join(
        [
            str(file_path),
            str(candidate_id),
            str(revert_start),
            str(revert_end),
            str(rewritten_text),
            str(previous_text),
            str(applied_file_hash),
        ]
    )
    return hmac.new(
        _rewrite_signature_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _compute_file_change_signature(
    *,
    logical_key: str,
    path: str,
    current_hash: str,
    pending_hash: str,
) -> str:
    payload = "\x1f".join(
        [
            str(logical_key),
            str(path),
            str(current_hash),
            str(pending_hash),
        ]
    )
    return hmac.new(
        _rewrite_signature_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _compute_file_change_revert_signature(
    *,
    logical_key: str,
    path: str,
    previous_hash: str,
    applied_hash: str,
) -> str:
    payload = "\x1f".join(
        [
            str(logical_key),
            str(path),
            str(previous_hash),
            str(applied_hash),
        ]
    )
    return hmac.new(
        _rewrite_signature_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _read_project_metadata(project: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    llm_config = cast(dict[str, Any], deepcopy(project.llm_config)) if isinstance(project.llm_config, dict) else {}
    metadata = cast(dict[str, Any], deepcopy(llm_config.get("metadata"))) if isinstance(llm_config.get("metadata"), dict) else {}
    if not isinstance(metadata.get("managed_files"), dict):
        metadata["managed_files"] = {}
    if not isinstance(metadata.get("file_changes"), list):
        metadata["file_changes"] = []
    if not isinstance(metadata.get("applied_file_changes"), dict):
        metadata["applied_file_changes"] = {}
    return llm_config, metadata


async def _record_latex_reference_usage(
    db: AsyncSession,
    *,
    workspace_id: str | None,
    latex_project_id: str,
    path: str,
    content: str,
) -> None:
    normalized_workspace_id = str(workspace_id or "").strip()
    if not normalized_workspace_id:
        return
    citation_keys = extract_citation_keys_from_text(content)
    if not citation_keys:
        return
    try:
        result = await db.execute(
            select(WorkspaceReference.citation_key).where(
                WorkspaceReference.workspace_id == normalized_workspace_id,
                WorkspaceReference.citation_key.in_(citation_keys),
                WorkspaceReference.is_deleted.is_(False),
            )
        )
        matched_keys = [str(item) for item in result.scalars().all()]
        if not matched_keys:
            return
        await ReferenceUsageService(db).record_usage_by_citation_keys(
            workspace_id=normalized_workspace_id,
            citation_keys=matched_keys,
            latex_project_id=latex_project_id,
            target_section=path,
            generated_text=content[:4000],
            usage_type="citation_only",
            accepted_status="accepted",
        )
    except Exception:
        logger.warning(
            "Failed to record LaTeX reference usage for project=%s workspace=%s",
            latex_project_id,
            normalized_workspace_id,
            exc_info=True,
        )


def _find_file_change(metadata: dict[str, Any], logical_key: str) -> dict[str, Any]:
    changes = metadata.get("file_changes")
    if not isinstance(changes, list):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File change not found")
    for item in changes:
        if isinstance(item, dict) and str(item.get("logical_key") or "") == logical_key:
            return dict(item)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File change not found")


def _remove_file_change(metadata: dict[str, Any], logical_key: str) -> None:
    changes = metadata.get("file_changes")
    if not isinstance(changes, list):
        metadata["file_changes"] = []
        return
    metadata["file_changes"] = [
        item
        for item in changes
        if not (isinstance(item, dict) and str(item.get("logical_key") or "") == logical_key)
    ]


def _pending_content_from_change(change: dict[str, Any]) -> str:
    pending_content = change.get("pending_content")
    if not isinstance(pending_content, str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "missing_pending_content",
                "message": "Pending file change is missing generated content.",
            },
        )
    return pending_content


def _preview_file_change_payload(
    *,
    logical_key: str,
    path: str,
    reason: str,
    current_content: str,
    pending_content: str,
) -> LatexFileChangePreviewResponse:
    current_hash = compute_content_hash(current_content)
    pending_hash = compute_content_hash(pending_content)
    diff_payload = build_latex_rewrite_diff(
        original_text=current_content,
        rewritten_text=pending_content,
        target_start=0,
        target_end=len(current_content),
        scope="section",
        resolved_selection_start=0,
        resolved_selection_end=len(current_content),
    )
    return LatexFileChangePreviewResponse(
        ok=True,
        logical_key=logical_key,
        path=path,
        reason=reason,
        current_hash=current_hash,
        pending_hash=pending_hash,
        change_signature=_compute_file_change_signature(
            logical_key=logical_key,
            path=path,
            current_hash=current_hash,
            pending_hash=pending_hash,
        ),
        diff=LatexDiffPayload.model_validate(diff_payload),
    )


@lru_cache(maxsize=1)
def _rewrite_compile_guard_enabled() -> bool:
    raw = str(os.getenv("WENJIN_LATEX_REWRITE_ENFORCE_COMPILE", "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _profiled_comment(comment: str, profile: RewriteProfile) -> str:
    guidance = _REWRITE_PROFILE_GUIDANCE.get(profile, "").strip()
    base = str(comment or "").strip()
    if not guidance:
        return base
    return f"{base}\n\n【改写策略】\n{guidance}"


def _candidate_risk_level(
    *,
    risk_flags: list[str],
    tokens_changed: int,
) -> RewriteRiskLevel:
    high_flags = {"boundary_leak", "citation_drop", "label_drop", "brace_unbalanced"}
    if any(flag in high_flags for flag in risk_flags) or tokens_changed >= 120:
        return "high"
    if risk_flags or tokens_changed >= 45:
        return "medium"
    return "low"


def _build_rewrite_candidate(
    *,
    source_content: str,
    file_path: str,
    scope: Literal["selection", "section"],
    profile: RewriteProfile,
    rewrite_result: dict[str, Any],
) -> LatexFeedbackRewriteCandidatePayload:
    target_start = int(rewrite_result["target_start"])
    target_end = int(rewrite_result["target_end"])
    rewritten_text = str(rewrite_result["rewritten_text"])
    original_segment = str(source_content)[target_start:target_end]
    validate_rewrite_segment(
        original_text=original_segment,
        rewritten_text=rewritten_text,
        scope=scope,
        target_start=target_start,
        target_end=target_end,
        resolved_selection_start=int(rewrite_result["resolved_selection_start"]),
        resolved_selection_end=int(rewrite_result["resolved_selection_end"]),
    )
    proposed_content = (
        str(source_content)[:target_start]
        + rewritten_text
        + str(source_content)[target_end:]
    )
    updated_anchor = build_feedback_anchor(
        proposed_content,
        target_start,
        target_start + len(rewritten_text),
    )
    diff_payload = build_latex_rewrite_diff(
        original_text=original_segment,
        rewritten_text=rewritten_text,
        target_start=target_start,
        target_end=target_end,
        scope=scope,
        resolved_selection_start=int(rewrite_result["resolved_selection_start"]),
        resolved_selection_end=int(rewrite_result["resolved_selection_end"]),
    )
    diff_model = LatexDiffPayload.model_validate(diff_payload)
    risk_level = _candidate_risk_level(
        risk_flags=list(diff_model.risk_flags),
        tokens_changed=int(diff_model.stats.tokens_changed),
    )
    candidate_id = uuid4().hex
    base_file_hash = compute_content_hash(str(source_content))
    base_range_hash = compute_range_hash(target_start, target_end, original_segment)
    return LatexFeedbackRewriteCandidatePayload(
        candidate_id=candidate_id,
        candidate_signature=_compute_candidate_signature(
            file_path=file_path,
            candidate_id=candidate_id,
            target_start=target_start,
            target_end=target_end,
            rewritten_text=rewritten_text,
            base_file_hash=base_file_hash,
            base_range_hash=base_range_hash,
        ),
        profile=profile,
        risk_level=risk_level,
        model_id=str(rewrite_result.get("model_id") or "default"),
        scope=scope,
        section_title=str(rewrite_result.get("section_title") or "未命名章节"),
        section_level=str(rewrite_result.get("section_level") or "section"),
        target_start=target_start,
        target_end=target_end,
        rewritten_text=rewritten_text,
        changes_summary=str(rewrite_result.get("changes_summary") or ""),
        proposed_content=proposed_content,
        updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
        base_file_hash=base_file_hash,
        base_range_hash=base_range_hash,
        diff=diff_model,
    )


async def _generate_rewrite_candidates(
    *,
    source_content: str,
    request: LatexFeedbackRewriteRequest,
) -> list[tuple[LatexFeedbackRewriteCandidatePayload, dict[str, Any]]]:
    requested_count = int(request.candidate_count or _MAX_REWRITE_CANDIDATES)
    requested_count = max(1, min(_MAX_REWRITE_CANDIDATES, requested_count))
    profiles = list(_REWRITE_PROFILE_ORDER[:requested_count])

    async def run_profile(profile: RewriteProfile) -> dict[str, Any]:
        task = rewrite_with_feedback(
            content=str(source_content),
            comment=_profiled_comment(request.comment, profile),
            selected_text=request.selected_text,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
            anchor=request.anchor.model_dump(mode="json") if request.anchor else None,
            scope=request.scope,
            requested_model_id=request.model_id,
        )
        try:
            return await asyncio.wait_for(
                task,
                timeout=_REWRITE_CANDIDATE_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise RuntimeError(f"rewrite candidate timed out: {profile}") from exc

    tasks = [run_profile(profile) for profile in profiles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    candidate_pairs: list[tuple[LatexFeedbackRewriteCandidatePayload, dict[str, Any]]] = []
    seen_rewrites: set[str] = set()
    first_error: Exception | None = None

    for profile, result in zip(profiles, results, strict=False):
        if isinstance(result, Exception):
            if first_error is None:
                first_error = result
            continue
        try:
            candidate = _build_rewrite_candidate(
                source_content=str(source_content),
                file_path=request.file_path,
                scope=request.scope,
                profile=profile,
                rewrite_result=result,
            )
        except LatexStructureValidationError as exc:
            if first_error is None:
                first_error = ValueError(
                    f"unsafe rewrite candidate rejected ({profile}): {exc.code}",
                )
            continue
        signature = candidate.rewritten_text.strip()
        if signature in seen_rewrites:
            continue
        seen_rewrites.add(signature)
        candidate_pairs.append((candidate, result))

    if candidate_pairs:
        return candidate_pairs

    if first_error is not None:
        raise first_error
    raise RuntimeError("Model did not return rewrite candidates")
