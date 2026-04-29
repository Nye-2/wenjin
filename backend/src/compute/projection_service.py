"""Projection service for the Compute Stage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.compute.events import serialize_compute_session
from src.database.models.compute_session import ComputeSessionRecord
from src.database.models.execution_session import ExecutionSessionRecord
from src.database.models.latex_project import LatexProject
from src.database.models.subagent_task import SubagentTaskRecord
from src.database.models.task import TaskRecord
from src.execution.public_paths import sandbox_path_to_public_url
from src.services.execution_session_events import serialize_execution_session
from src.workspace_features.runtime_profiles import get_feature_runtime_profile

_FILE_PATH_KEYS = {
    "sandbox_path",
    "figure_path",
    "file_path",
    "pdf_path",
    "manifest_path",
    "source_path",
    "output_path",
}
_FILE_URL_KEYS = {
    "file_url",
    "pdf_url",
    "pdf_endpoint",
    "manifest_url",
    "stored_url",
    "public_url",
    "url",
}
_FILE_LIST_KEYS = {
    "artifact_ids",
    "output_files",
    "files",
    "generated_files",
    "extra_files",
}
_LOG_KEYS = {
    "logs",
    "compile_logs",
    "log",
    "stdout",
    "stderr",
    "error_message",
    "execution_error",
}
_LOG_MAX_CHARS = 4000
_PRISM_REQUIRED_ACTIONS = {
    "artifact_promote",
    "confirm",
    "latex_apply",
    "latex_revert",
    "review",
    "user_input_required",
}
_PRISM_OPTIONAL_ACTIONS = {
    "open_prism",
    "open_latex",
}


def _task_payload(record: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": record.id,
        "execution_session_id": record.execution_session_id,
        "task_type": record.task_type,
        "workspace_id": record.workspace_id,
        "feature_id": record.feature_id,
        "thread_id": record.thread_id,
        "action": record.action,
        "status": record.status,
        "progress": record.progress,
        "message": record.message,
        "result": record.result,
        "error": record.error,
        "runtime_state": record.runtime_state,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def _subagent_payload(record: SubagentTaskRecord) -> dict[str, Any]:
    return {
        "task_id": record.id,
        "workspace_id": record.workspace_id,
        "thread_id": record.thread_id,
        "execution_session_id": record.execution_session_id,
        "subagent_type": record.subagent_type,
        "status": record.status,
        "input_prompt": record.prompt,
        "output_preview": record.output_preview,
        "error": record.error,
        "metadata": record.task_metadata or {},
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def _runtime_blocks(execution: ExecutionSessionRecord) -> list[dict[str, Any]]:
    snapshot = execution.runtime_snapshot if isinstance(execution.runtime_snapshot, dict) else {}
    blocks = snapshot.get("blocks")
    if not isinstance(blocks, list):
        return []
    return [dict(block) for block in blocks if isinstance(block, dict)]


def _clip_text(value: str, *, max_chars: int = _LOG_MAX_CHARS) -> tuple[str, bool]:
    text = value.strip()
    if len(text) <= max_chars:
        return text, False
    return f"{text[:max_chars].rstrip()}\n...", True


def _read_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _append_file(
    files: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    source: str,
    kind: str,
    label: str,
    path: str | None = None,
    url: str | None = None,
    artifact_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    thread_id: str | None = None,
) -> None:
    path = path.strip() if isinstance(path, str) else None
    url = url.strip() if isinstance(url, str) else None
    artifact_id = artifact_id.strip() if isinstance(artifact_id, str) else None
    if not path and not url and not artifact_id:
        return

    public_url = url
    if public_url is None and path:
        public_url = sandbox_path_to_public_url(path, thread_id=thread_id)

    key = (kind, artifact_id or path or "", public_url or "")
    if key in seen:
        return
    seen.add(key)
    files.append(
        {
            "id": f"{kind}:{len(files) + 1}",
            "kind": kind,
            "label": label,
            "source": source,
            "path": path,
            "url": public_url,
            "artifact_id": artifact_id,
            "metadata": metadata or {},
        }
    )


def _extract_files_from_value(
    value: Any,
    *,
    source: str,
    thread_id: str | None,
    files: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    key_hint: str | None = None,
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _FILE_PATH_KEYS:
                text = _read_text(nested)
                if text is not None:
                    _append_file(
                        files,
                        seen,
                        source=source,
                        kind="sandbox_file" if text.startswith("/mnt/user-data/") else "file",
                        label=key_text,
                        path=text,
                        metadata={"field": key_text},
                        thread_id=thread_id,
                    )
                    continue
            if key_text in _FILE_URL_KEYS:
                text = _read_text(nested)
                if text is not None:
                    _append_file(
                        files,
                        seen,
                        source=source,
                        kind="linked_file",
                        label=key_text,
                        url=text,
                        metadata={"field": key_text},
                        thread_id=thread_id,
                    )
                    continue
            if key_text in _FILE_LIST_KEYS and isinstance(nested, list):
                for index, item in enumerate(nested):
                    if isinstance(item, str):
                        text = item.strip()
                        if not text:
                            continue
                        if key_text == "artifact_ids":
                            _append_file(
                                files,
                                seen,
                                source=source,
                                kind="artifact",
                                label=text,
                                artifact_id=text,
                                metadata={"field": key_text, "index": index},
                                thread_id=thread_id,
                            )
                        else:
                            _append_file(
                                files,
                                seen,
                                source=source,
                                kind="output_file",
                                label=text.rsplit("/", 1)[-1] or text,
                                path=text,
                                metadata={"field": key_text, "index": index},
                                thread_id=thread_id,
                            )
                    elif isinstance(item, dict):
                        _extract_files_from_value(
                            item,
                            source=source,
                            thread_id=thread_id,
                            files=files,
                            seen=seen,
                            key_hint=f"{key_text}[{index}]",
                        )
                continue
            _extract_files_from_value(
                nested,
                source=source,
                thread_id=thread_id,
                files=files,
                seen=seen,
                key_hint=key_text,
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _extract_files_from_value(
                item,
                source=source,
                thread_id=thread_id,
                files=files,
                seen=seen,
                key_hint=f"{key_hint or 'items'}[{index}]",
            )


def _collect_files(
    *,
    execution: ExecutionSessionRecord,
    tasks: list[TaskRecord],
    runtime_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    thread_id = execution.thread_id
    for artifact_id in execution.artifact_ids or []:
        text = str(artifact_id).strip()
        if text:
            _append_file(
                files,
                seen,
                source="execution",
                kind="artifact",
                label=text,
                artifact_id=text,
                metadata={"field": "artifact_ids"},
                thread_id=thread_id,
            )

    _extract_files_from_value(
        execution.runtime_snapshot,
        source="runtime",
        thread_id=thread_id,
        files=files,
        seen=seen,
    )
    for block in runtime_blocks:
        _extract_files_from_value(
            block,
            source="runtime",
            thread_id=thread_id,
            files=files,
            seen=seen,
        )
    for task in tasks:
        task_source = f"task:{task.id}"
        _extract_files_from_value(
            task.result,
            source=task_source,
            thread_id=task.thread_id or thread_id,
            files=files,
            seen=seen,
        )
        _extract_files_from_value(
            task.runtime_state,
            source=task_source,
            thread_id=task.thread_id or thread_id,
            files=files,
            seen=seen,
        )
    return files


def _normalize_prism_file_changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_applied_prism_file_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _append_unique_text(values: list[str], value: Any) -> None:
    text = _read_text(value)
    if text is None or text in values:
        return
    values.append(text)


def _collect_section_map_files(section_map: Any, target_files: list[str]) -> None:
    if not isinstance(section_map, dict):
        return
    for value in section_map.values():
        _append_unique_text(target_files, value)


def _prism_payload_from_dict(value: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    latex_project_id = _read_text(value.get("latex_project_id"))
    if latex_project_id is None:
        return None

    target_files: list[str] = []
    main_file = _read_text(value.get("main_file")) or "main.tex"
    _append_unique_text(target_files, main_file)
    _append_unique_text(target_files, value.get("section_file"))
    _collect_section_map_files(value.get("section_map"), target_files)
    for change in _normalize_prism_file_changes(value.get("file_changes")):
        _append_unique_text(target_files, change.get("path"))
    for change in _normalize_applied_prism_file_changes(value.get("applied_file_changes")):
        _append_unique_text(target_files, change.get("path"))

    compile_status = _read_text(value.get("compile_status"))
    compile_error = _read_text(value.get("compile_error"))
    compile = {
        "status": compile_status,
        "pdf_path": _read_text(value.get("pdf_path")),
        "pdf_url": _read_text(value.get("pdf_url")) or _read_text(value.get("pdf_endpoint")),
        "pdf_endpoint": _read_text(value.get("pdf_endpoint")),
        "page_count": value.get("page_count") if isinstance(value.get("page_count"), int) else None,
        "error": compile_error,
    }
    file_changes = _normalize_prism_file_changes(value.get("file_changes"))
    applied_file_changes = _normalize_applied_prism_file_changes(value.get("applied_file_changes"))
    status = "ready"
    if compile_status == "failed" or compile_error:
        status = "compile_failed"
    elif file_changes:
        status = "pending_changes"

    return {
        "id": f"prism:{latex_project_id}:{source}",
        "source": source,
        "status": status,
        "latex_project_id": latex_project_id,
        "url": _read_text(value.get("prism_url")) or f"/latex/{latex_project_id}",
        "main_file": main_file,
        "section_file": _read_text(value.get("section_file")),
        "target_files": target_files,
        "section_map": dict(value.get("section_map")) if isinstance(value.get("section_map"), dict) else {},
        "file_changes": file_changes,
        "applied_file_changes": applied_file_changes,
        "compile": compile,
    }


def _collect_prism_items_from_value(
    value: Any,
    *,
    source: str,
    items: list[dict[str, Any]],
    seen: set[tuple[str, str, tuple[str, ...]]],
) -> None:
    if isinstance(value, dict):
        candidate = _prism_payload_from_dict(value, source=source)
        if candidate is not None:
            key = (
                str(candidate["latex_project_id"]),
                str(candidate["source"]),
                tuple(candidate["target_files"]),
            )
            if key not in seen:
                seen.add(key)
                items.append(candidate)
        for nested in value.values():
            _collect_prism_items_from_value(
                nested,
                source=source,
                items=items,
                seen=seen,
            )
        return

    if isinstance(value, list):
        for nested in value:
            _collect_prism_items_from_value(
                nested,
                source=source,
                items=items,
                seen=seen,
            )


def _build_prism_projection(
    *,
    execution: ExecutionSessionRecord,
    tasks: list[TaskRecord],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    _collect_prism_items_from_value(
        execution.runtime_snapshot,
        source="runtime",
        items=items,
        seen=seen,
    )
    for task in tasks:
        source = f"task:{task.id}"
        _collect_prism_items_from_value(
            task.result,
            source=source,
            items=items,
            seen=seen,
        )
        _collect_prism_items_from_value(
            task.runtime_state,
            source=source,
            items=items,
            seen=seen,
        )

    primary = items[0] if items else None
    target_files: list[str] = []
    file_changes: list[dict[str, Any]] = []
    applied_file_changes: list[dict[str, Any]] = []
    for item in items:
        for path in item.get("target_files", []):
            _append_unique_text(target_files, path)
        for change in item.get("file_changes", []):
            if isinstance(change, dict) and change not in file_changes:
                file_changes.append(dict(change))
        for change in item.get("applied_file_changes", []):
            if isinstance(change, dict) and change not in applied_file_changes:
                applied_file_changes.append(dict(change))

    status = "unbound"
    if primary is not None:
        status = "ready"
        if any(item.get("status") == "compile_failed" for item in items):
            status = "compile_failed"
        elif file_changes:
            status = "pending_changes"

    return {
        "status": status,
        "project_id": primary.get("latex_project_id") if primary is not None else None,
        "url": primary.get("url") if primary is not None else None,
        "main_file": primary.get("main_file") if primary is not None else None,
        "target_files": target_files,
        "file_changes": file_changes,
        "applied_file_changes": applied_file_changes,
        "compile": primary.get("compile") if primary is not None else {},
        "items": items,
    }


async def _refresh_prism_from_project(
    db: AsyncSession,
    prism: dict[str, Any],
    *,
    user_id: str,
) -> dict[str, Any]:
    project_id = _read_text(prism.get("project_id"))
    if project_id is None:
        return prism

    result = await db.execute(
        select(LatexProject).where(
            LatexProject.id == project_id,
            LatexProject.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        return prism

    llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
    metadata = llm_config.get("metadata") if isinstance(llm_config.get("metadata"), dict) else {}
    current_file_changes = _normalize_prism_file_changes(metadata.get("file_changes"))
    current_applied_file_changes = _normalize_applied_prism_file_changes(
        metadata.get("applied_file_changes")
    )
    prism["file_changes"] = current_file_changes
    prism["applied_file_changes"] = current_applied_file_changes
    prism["main_file"] = str(project.main_file or prism.get("main_file") or "main.tex")
    for change in current_file_changes:
        _append_unique_text(prism.setdefault("target_files", []), change.get("path"))
    for change in current_applied_file_changes:
        _append_unique_text(prism.setdefault("target_files", []), change.get("path"))
    compile_info = prism.get("compile") if isinstance(prism.get("compile"), dict) else {}
    status = "ready"
    if compile_info.get("status") == "failed" or compile_info.get("error"):
        status = "compile_failed"
    elif current_file_changes:
        status = "pending_changes"
    prism["status"] = status
    for item in prism.get("items", []):
        if not isinstance(item, dict) or item.get("latex_project_id") != project_id:
            continue
        item["file_changes"] = current_file_changes
        item["applied_file_changes"] = current_applied_file_changes
        item_status = "ready"
        item_compile = item.get("compile") if isinstance(item.get("compile"), dict) else {}
        if item_compile.get("status") == "failed" or item_compile.get("error"):
            item_status = "compile_failed"
        elif current_file_changes:
            item_status = "pending_changes"
        item["status"] = item_status
    return prism


def _append_prism_files(files: list[dict[str, Any]], prism: dict[str, Any]) -> None:
    project_id = _read_text(prism.get("project_id"))
    if project_id is None:
        return
    url = _read_text(prism.get("url")) or f"/latex/{project_id}"
    seen = {
        (
            str(item.get("kind") or ""),
            str(item.get("artifact_id") or item.get("path") or ""),
            str(item.get("url") or ""),
        )
        for item in files
    }
    for path in prism.get("target_files", []):
        path_text = _read_text(path)
        if path_text is None:
            continue
        _append_file(
            files,
            seen,
            source="prism",
            kind="prism_file",
            label=path_text,
            path=path_text,
            url=url,
            metadata={"latex_project_id": project_id},
        )


def _append_log(
    logs: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    source: str,
    level: str,
    title: str,
    message: str | None,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not message:
        return
    clipped, truncated = _clip_text(message)
    key = (source, title, clipped)
    if key in seen:
        return
    seen.add(key)
    logs.append(
        {
            "id": f"log:{len(logs) + 1}",
            "source": source,
            "level": level,
            "title": title,
            "message": clipped,
            "timestamp": timestamp,
            "truncated": truncated,
            "metadata": metadata or {},
        }
    )


def _log_level_from_key(key: str, *, default: str = "info") -> str:
    if key in {"stderr", "error_message", "execution_error"}:
        return "error"
    if key == "compile_logs":
        return "warning"
    return default


def _collect_log_fields(
    value: Any,
    *,
    source: str,
    logs: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _LOG_KEYS:
                text = _read_text(nested)
                if text is not None:
                    _append_log(
                        logs,
                        seen,
                        source=source,
                        level=_log_level_from_key(key_text),
                        title=key_text,
                        message=text,
                        metadata={"field": key_text},
                    )
                    continue
            _collect_log_fields(nested, source=source, logs=logs, seen=seen)
        return

    if isinstance(value, list):
        for item in value:
            _collect_log_fields(item, source=source, logs=logs, seen=seen)


def _collect_runtime_activity_logs(
    runtime_blocks: list[dict[str, Any]],
    *,
    logs: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
) -> None:
    tone_to_level = {
        "success": "success",
        "warning": "warning",
        "danger": "error",
        "info": "info",
    }
    for block in runtime_blocks:
        if block.get("kind") != "activity" or not isinstance(block.get("items"), list):
            continue
        for item in block["items"]:
            if not isinstance(item, dict):
                continue
            title = _read_text(item.get("title")) or "Runtime activity"
            description = _read_text(item.get("description")) or title
            tone = _read_text(item.get("tone")) or "info"
            _append_log(
                logs,
                seen,
                source="runtime",
                level=tone_to_level.get(tone, "info"),
                title=title,
                message=description,
                timestamp=_read_text(item.get("timestamp")),
                metadata={"block_id": block.get("id")},
            )


def _collect_logs(
    *,
    execution: ExecutionSessionRecord,
    tasks: list[TaskRecord],
    runtime_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    _collect_runtime_activity_logs(runtime_blocks, logs=logs, seen=seen)
    if execution.last_error:
        _append_log(
            logs,
            seen,
            source="execution",
            level="error",
            title="Execution error",
            message=execution.last_error,
            timestamp=execution.updated_at.isoformat() if execution.updated_at else None,
        )
    for task in tasks:
        task_source = f"task:{task.id}"
        if task.message:
            _append_log(
                logs,
                seen,
                source=task_source,
                level="info",
                title="Task message",
                message=task.message,
                timestamp=task.completed_at.isoformat() if task.completed_at else task.started_at.isoformat() if task.started_at else None,
                metadata={"status": task.status},
            )
        if task.error:
            _append_log(
                logs,
                seen,
                source=task_source,
                level="error",
                title="Task error",
                message=task.error,
                timestamp=task.completed_at.isoformat() if task.completed_at else None,
                metadata={"status": task.status},
            )
        _collect_log_fields(task.result, source=task_source, logs=logs, seen=seen)
        _collect_log_fields(task.runtime_state, source=task_source, logs=logs, seen=seen)
    return logs


def _review_item_label(item: dict[str, Any]) -> str:
    for key in ("title", "label", "message", "description", "action", "kind", "type"):
        text = _read_text(item.get(key))
        if text is not None:
            return text
    return "Review action"


def _review_item_required(item: dict[str, Any]) -> bool:
    raw_required = item.get("required")
    if isinstance(raw_required, bool):
        return raw_required
    action = _read_text(item.get("kind")) or _read_text(item.get("action")) or _read_text(item.get("type"))
    if action in _PRISM_OPTIONAL_ACTIONS:
        return False
    if action in _PRISM_REQUIRED_ACTIONS:
        return True
    return False


def _build_review_gate(execution: ExecutionSessionRecord) -> dict[str, Any]:
    next_actions = [dict(item) for item in execution.next_actions or [] if isinstance(item, dict)]
    items = [
        {
            "id": f"review:{index + 1}",
            "kind": _read_text(action.get("kind")) or _read_text(action.get("type")) or "action",
            "label": _review_item_label(action),
            "required": _review_item_required(action),
            "payload": action,
        }
        for index, action in enumerate(next_actions)
    ]
    has_required_item = any(item["required"] for item in items)
    status = "clear"
    if execution.advisory_code or has_required_item:
        status = "awaiting_user"
    elif execution.status == "failed":
        status = "failed"
    elif items:
        status = "advisory"

    return {
        "status": status,
        "required": status == "awaiting_user",
        "policy": _build_runtime_profile_projection(execution).get("review_gate"),
        "next_actions": next_actions,
        "items": items,
        "advisory_code": execution.advisory_code,
    }


def _build_runtime_profile_projection(execution: ExecutionSessionRecord) -> dict[str, Any]:
    profile = get_feature_runtime_profile(
        str(execution.workspace_type or ""),
        str(execution.feature_id or ""),
    )
    if profile is None:
        return {}
    return {
        "workspace_type": profile.workspace_type,
        "feature_id": profile.feature_id,
        "runtime_mode": str(profile.runtime_mode),
        "requires_compute": profile.requires_compute,
        "requires_sandbox": profile.requires_sandbox,
        "allowed_subagents": list(profile.allowed_subagents),
        "max_subagents": profile.max_subagents,
        "agent_harness_provider": profile.agent_harness_provider,
        "output_contract": profile.output_contract,
        "review_gate": profile.review_gate,
    }


def _build_sandbox_projection(
    *,
    compute_session: ComputeSessionRecord,
    files: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    runtime_profile: dict[str, Any],
) -> dict[str, Any]:
    has_sandbox_files = any(item.get("kind") == "sandbox_file" for item in files)
    requires_sandbox = bool(runtime_profile.get("requires_sandbox"))
    if compute_session.sandbox_session_id:
        status = "bound"
    elif has_sandbox_files:
        status = "derived"
    elif requires_sandbox:
        status = "required"
    else:
        status = "unbound"
    return {
        "session_id": compute_session.sandbox_session_id,
        "status": status,
        "required": requires_sandbox,
        "files": files,
        "logs": logs,
        "file_count": len(files),
        "log_count": len(logs),
    }


class ComputeProjectionService:
    """Build frontend-facing projections without making compute a business source of truth."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_projection(
        self,
        *,
        compute_session_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(ComputeSessionRecord).where(
                ComputeSessionRecord.id == compute_session_id,
                ComputeSessionRecord.user_id == user_id,
            )
        )
        compute_session = result.scalar_one_or_none()
        if compute_session is None:
            return None

        execution_result = await self.db.execute(
            select(ExecutionSessionRecord).where(
                ExecutionSessionRecord.id == compute_session.execution_session_id,
                ExecutionSessionRecord.user_id == user_id,
            )
        )
        execution = execution_result.scalar_one_or_none()
        if execution is None:
            return None

        task_ids = {
            str(task_id).strip()
            for task_id in [
                execution.primary_task_id,
                *list(execution.task_ids or []),
            ]
            if str(task_id or "").strip()
        }
        tasks: list[TaskRecord] = []
        if task_ids:
            task_result = await self.db.execute(
                select(TaskRecord)
                .where(
                    TaskRecord.id.in_(sorted(task_ids)),
                    TaskRecord.user_id == user_id,
                )
                .order_by(TaskRecord.created_at.desc())
            )
            tasks = list(task_result.scalars().all())

        subagent_result = await self.db.execute(
            select(SubagentTaskRecord)
            .where(
                SubagentTaskRecord.execution_session_id == execution.id,
                SubagentTaskRecord.user_id == user_id,
            )
            .order_by(SubagentTaskRecord.created_at.desc())
        )
        subagents = list(subagent_result.scalars().all())

        primary_task = next(
            (task for task in tasks if task.id == execution.primary_task_id),
            tasks[0] if tasks else None,
        )
        runtime_blocks = _runtime_blocks(execution)
        files = _collect_files(
            execution=execution,
            tasks=tasks,
            runtime_blocks=runtime_blocks,
        )
        prism = _build_prism_projection(
            execution=execution,
            tasks=tasks,
        )
        prism = await _refresh_prism_from_project(
            self.db,
            prism,
            user_id=user_id,
        )
        _append_prism_files(files, prism)
        logs = _collect_logs(
            execution=execution,
            tasks=tasks,
            runtime_blocks=runtime_blocks,
        )
        runtime_profile = _build_runtime_profile_projection(execution)
        review_gate = _build_review_gate(execution)
        return {
            "compute_session": serialize_compute_session(compute_session),
            "execution": serialize_execution_session(execution),
            "runtime_profile": runtime_profile,
            "primary_task": _task_payload(primary_task) if primary_task is not None else None,
            "tasks": [_task_payload(task) for task in tasks],
            "runtime_blocks": runtime_blocks,
            "subagents": [_subagent_payload(record) for record in subagents],
            "artifacts": {
                "ids": list(execution.artifact_ids or []),
                "count": len(execution.artifact_ids or []),
            },
            "sandbox": _build_sandbox_projection(
                compute_session=compute_session,
                files=files,
                logs=logs,
                runtime_profile=runtime_profile,
            ),
            "prism": prism,
            "files": files,
            "logs": logs,
            "review_gate": review_gate,
        }
