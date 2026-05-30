"""Projection service for the Compute Stage."""

from __future__ import annotations

from typing import Any

from src.compute.events import serialize_compute_session
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.execution import (
    ComputeSessionPayload,
    ExecutionNodePayload,
    ExecutionPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.execution.public_paths import sandbox_path_to_public_url
from src.services.execution_service import serialize_execution_record

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
    "preview_prism_changes",
    "review",
    "user_input_required",
}
_PRISM_OPTIONAL_ACTIONS = {
    "open_prism",
}


def _execution_task_payload(record: ExecutionPayload) -> dict[str, Any]:
    return {
        "task_id": record.id,
        "execution_id": record.id,
        "task_type": record.execution_type,
        "workspace_id": record.workspace_id,
        "feature_id": record.feature_id,
        "thread_id": record.thread_id,
        "action": record.params.get("action") if isinstance(record.params, dict) else None,
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


def _node_payload(
    record: ExecutionNodePayload,
    *,
    execution: ExecutionPayload,
) -> dict[str, Any]:
    output_data = record.output_data if isinstance(record.output_data, dict) else {}
    input_data = record.input_data if isinstance(record.input_data, dict) else {}
    error = output_data.get("error")
    input_prompt = input_data.get("prompt") or input_data.get("input_prompt")
    output_preview = (
        output_data.get("output_preview")
        or output_data.get("summary")
        or output_data.get("message")
        or error
    )
    return {
        "task_id": record.id,
        "node_id": record.node_id,
        "workspace_id": execution.workspace_id,
        "thread_id": execution.thread_id,
        "execution_id": record.execution_id,
        "subagent_type": record.node_type,
        "label": record.label,
        "status": record.status,
        "input_prompt": str(input_prompt) if input_prompt is not None else None,
        "output_preview": str(output_preview) if output_preview is not None else None,
        "error": str(error) if error is not None else None,
        "metadata": record.node_metadata or {},
        "input": record.input_data,
        "output": record.output_data,
        "thinking": record.thinking,
        "tool_calls": record.tool_calls or [],
        "token_usage": record.token_usage or {},
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def _runtime_blocks(execution: ExecutionPayload) -> list[dict[str, Any]]:
    snapshot = execution.runtime_state if isinstance(execution.runtime_state, dict) else {}
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
    execution: ExecutionPayload,
    nodes: list[ExecutionNodePayload],
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
        execution.runtime_state,
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
    _extract_files_from_value(
        execution.result,
        source="execution",
        thread_id=thread_id,
        files=files,
        seen=seen,
    )
    for node in nodes:
        node_source = f"node:{node.node_id}"
        _extract_files_from_value(
            node.input_data,
            source=node_source,
            thread_id=thread_id,
            files=files,
            seen=seen,
        )
        _extract_files_from_value(
            node.output_data,
            source=node_source,
            thread_id=thread_id,
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


def _empty_prism_projection() -> dict[str, Any]:
    return {
        "status": "unbound",
        "project_id": None,
        "url": None,
        "main_file": None,
        "target_files": [],
        "file_changes": [],
        "applied_file_changes": [],
        "compile": {},
        "items": [],
    }


def _build_prism_projection_from_surface(
    surface: dict[str, Any],
) -> dict[str, Any]:
    project_id = _read_text(surface.get("latex_project_id"))
    file_changes = _normalize_prism_file_changes(surface.get("file_changes"))
    applied_file_changes = _normalize_applied_prism_file_changes(
        surface.get("applied_file_changes")
    )
    target_files: list[str] = []
    for path in surface.get("target_files", []):
        _append_unique_text(target_files, path)
    if not target_files:
        _append_unique_text(target_files, surface.get("main_file"))
        for change in file_changes:
            _append_unique_text(target_files, change.get("path"))
        for change in applied_file_changes:
            _append_unique_text(target_files, change.get("path"))

    compile_status = _read_text(surface.get("compile_status"))
    status = "ready"
    if compile_status == "failed":
        status = "compile_failed"
    elif bool(surface.get("has_pending_changes")) or file_changes:
        status = "pending_changes"

    return {
        "status": status,
        "project_id": project_id,
        "url": _read_text(surface.get("url")),
        "main_file": _read_text(surface.get("main_file")),
        "target_files": target_files,
        "file_changes": file_changes,
        "applied_file_changes": applied_file_changes,
        "compile": {"status": compile_status} if compile_status else {},
        "items": _normalize_prism_file_changes(surface.get("review_items")),
    }


def _append_prism_files(files: list[dict[str, Any]], prism: dict[str, Any]) -> None:
    project_id = _read_text(prism.get("project_id"))
    url = _read_text(prism.get("url"))
    if project_id is None or url is None:
        return
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
    execution: ExecutionPayload,
    nodes: list[ExecutionNodePayload],
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
    if execution.message:
        _append_log(
            logs,
            seen,
            source="execution",
            level="info",
            title="Execution message",
            message=execution.message,
            timestamp=(
                execution.completed_at.isoformat()
                if execution.completed_at
                else execution.started_at.isoformat()
                if execution.started_at
                else None
            ),
            metadata={"status": execution.status},
        )
    if execution.error:
        _append_log(
            logs,
            seen,
            source="execution",
            level="error",
            title="Execution error",
            message=execution.error,
            timestamp=execution.completed_at.isoformat() if execution.completed_at else None,
            metadata={"status": execution.status},
        )
    _collect_log_fields(execution.result, source="execution", logs=logs, seen=seen)
    _collect_log_fields(execution.runtime_state, source="runtime", logs=logs, seen=seen)
    for node in nodes:
        node_source = f"node:{node.node_id}"
        output_data = node.output_data if isinstance(node.output_data, dict) else {}
        error = _read_text(output_data.get("error"))
        if error is not None:
            _append_log(
                logs,
                seen,
                source=node_source,
                level="error",
                title=node.label or node.node_id,
                message=error,
                timestamp=node.completed_at.isoformat() if node.completed_at else None,
                metadata={"status": node.status, "node_type": node.node_type},
            )
        _collect_log_fields(node.input_data, source=node_source, logs=logs, seen=seen)
        _collect_log_fields(node.output_data, source=node_source, logs=logs, seen=seen)
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


def _build_review_gate(
    execution: ExecutionPayload,
    runtime_profile: dict[str, Any],
) -> dict[str, Any]:
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
        "policy": runtime_profile.get("review_gate"),
        "next_actions": next_actions,
        "items": items,
        "advisory_code": execution.advisory_code,
    }


async def _build_runtime_profile_projection(
    dataservice: AsyncDataServiceClient,
    execution: ExecutionPayload,
) -> dict[str, Any]:
    workspace_type = str(execution.workspace_type or "").strip()
    feature_id = str(execution.feature_id or "").strip()
    if not workspace_type or not feature_id:
        return {}
    capability = await dataservice.get_catalog_capability(
        capability_id=feature_id,
        workspace_type=workspace_type,
    )
    raw = capability.runtime if capability is not None else None
    if not isinstance(raw, dict):
        return {}
    definition_json = getattr(capability, "definition_json", None) if capability is not None else None
    if not isinstance(definition_json, dict):
        definition_json = {}
    sandbox_policy = definition_json.get("sandbox_policy")
    if not isinstance(sandbox_policy, dict):
        sandbox_policy = raw.get("sandbox_policy") if isinstance(raw.get("sandbox_policy"), dict) else {}

    review_gate_value = raw.get("review_gate")
    if isinstance(review_gate_value, dict) and review_gate_value:
        review_gate = _read_text(review_gate_value.get("kind"))
    elif isinstance(review_gate_value, str) and review_gate_value.strip():
        review_gate = review_gate_value.strip()
    else:
        review_gate = None

    allowed_paths_value = raw.get("allowed_paths")
    allowed_paths = (
        [str(item) for item in allowed_paths_value if isinstance(item, str)]
        if isinstance(allowed_paths_value, list)
        else []
    )

    return {
        "workspace_type": workspace_type,
        "feature_id": feature_id,
        "runtime_mode": str(raw.get("mode") or ""),
        "requires_sandbox": sandbox_policy.get("mode") == "required",
        "sandbox_policy": sandbox_policy,
        "review_gate": review_gate,
        "allowed_paths": allowed_paths,
    }


def _build_sandbox_projection(
    *,
    compute_session: ComputeSessionPayload,
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

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    async def get_projection(
        self,
        *,
        compute_session_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        if self._dataservice is not None:
            client = self._dataservice
            return await self._get_projection_with_client(
                client,
                compute_session_id=compute_session_id,
                user_id=user_id,
            )
        async with dataservice_client() as client:
            return await self._get_projection_with_client(
                client,
                compute_session_id=compute_session_id,
                user_id=user_id,
            )

    async def _get_projection_with_client(
        self,
        client: AsyncDataServiceClient,
        *,
        compute_session_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        compute_session = await client.get_compute_session(compute_session_id)
        if compute_session is None or str(compute_session.user_id) != str(user_id):
            return None
        execution = await client.get_execution(str(compute_session.execution_id))
        if execution is None or str(execution.user_id) != str(user_id):
            return None

        nodes = await client.list_execution_nodes(execution.id)
        primary_task = _execution_task_payload(execution)
        runtime_blocks = _runtime_blocks(execution)
        files = _collect_files(
            execution=execution,
            nodes=nodes,
            runtime_blocks=runtime_blocks,
        )
        prism = _empty_prism_projection()
        if execution.workspace_id:
            from src.services.workspace_prism_service import WorkspacePrismService

            try:
                surface = await WorkspacePrismService(
                    dataservice=client,
                ).get_surface_projection(
                    str(execution.workspace_id),
                    user_id=str(execution.user_id),
                )
            except ValueError:
                prism = _empty_prism_projection()
            else:
                prism = _build_prism_projection_from_surface(surface)
        _append_prism_files(files, prism)
        logs = _collect_logs(
            execution=execution,
            nodes=nodes,
            runtime_blocks=runtime_blocks,
        )
        runtime_profile = await _build_runtime_profile_projection(client, execution)
        review_gate = _build_review_gate(execution, runtime_profile)
        return {
            "compute_session": serialize_compute_session(compute_session),
            "execution": serialize_execution_record(execution),
            "runtime_profile": runtime_profile,
            "primary_task": primary_task,
            "tasks": [primary_task],
            "runtime_blocks": runtime_blocks,
            "subagents": [
                _node_payload(record, execution=execution) for record in nodes
            ],
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
