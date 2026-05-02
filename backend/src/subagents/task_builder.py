"""Shared helpers for normalized subagent task construction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .config import SubagentConfig
from .models import SubagentTask


def _normalize_optional_str(value: Any) -> str | None:
    """Normalize optional runtime identifiers to non-empty strings."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_positive_int(value: Any) -> int | None:
    """Normalize optional numeric limits from partially mocked configs."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    assert isinstance(value, int)
    return value


@dataclass(frozen=True, slots=True)
class SubagentRuntimeContext:
    """Normalized parent/runtime context for a subagent task."""

    thread_id: str | None = None
    workspace_id: str | None = None
    user_id: str | None = None
    execution_session_id: str | None = None
    model_name: str | None = None
    trace_id: str | None = None

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> SubagentRuntimeContext:
        """Build a normalized runtime context from a config/context mapping."""
        values = values or {}
        return cls(
            thread_id=_normalize_optional_str(values.get("thread_id")),
            workspace_id=_normalize_optional_str(values.get("workspace_id")),
            user_id=_normalize_optional_str(values.get("user_id")),
            execution_session_id=_normalize_optional_str(
                values.get("execution_session_id")
            ),
            model_name=_normalize_optional_str(values.get("model_name")),
            trace_id=_normalize_optional_str(values.get("trace_id")),
        )

    def resolve_thread_id(
        self,
        *,
        fallback_prefix: str,
    ) -> str:
        """Resolve a concrete thread id, generating one when detached."""
        if self.thread_id is not None:
            return self.thread_id
        suffix = self.trace_id or str(uuid4())
        return f"{fallback_prefix}-{suffix}"


def build_subagent_metadata(
    *,
    subagent_type: str | None = None,
    system_prompt: str | None = None,
    context_snapshot: str | None = None,
    description: str | None = None,
    runtime_context: SubagentRuntimeContext | None = None,
    include_workspace: bool = False,
    include_user: bool = False,
    include_execution_session: bool = True,
    include_model: bool = True,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Build normalized string metadata for a subagent task."""
    metadata: dict[str, str] = {}

    if description is not None:
        metadata["description"] = str(description)
    if subagent_type is not None:
        metadata["subagent_type"] = str(subagent_type)
    resolved_system_prompt = str(system_prompt) if system_prompt is not None else ""
    resolved_context_snapshot = str(context_snapshot) if context_snapshot is not None else ""
    if resolved_context_snapshot:
        if resolved_system_prompt:
            metadata["system_prompt"] = f"{resolved_system_prompt}\n\n{resolved_context_snapshot}"
        else:
            metadata["system_prompt"] = resolved_context_snapshot
    elif system_prompt is not None:
        metadata["system_prompt"] = resolved_system_prompt

    if runtime_context is not None:
        if include_workspace and runtime_context.workspace_id is not None:
            metadata["workspace_id"] = runtime_context.workspace_id
        if include_user and runtime_context.user_id is not None:
            metadata["user_id"] = runtime_context.user_id
        if (
            include_execution_session
            and runtime_context.execution_session_id is not None
        ):
            metadata["execution_session_id"] = runtime_context.execution_session_id
        if include_model and runtime_context.model_name is not None:
            metadata["model_name"] = runtime_context.model_name

    for key, value in (extra_metadata or {}).items():
        if value is None:
            continue
        metadata[str(key)] = str(value)

    return metadata


def build_subagent_task(
    manager_config: SubagentConfig,
    *,
    prompt: str,
    thread_id: str,
    fallback_max_turns: int,
    requested_max_turns: int | None = None,
    requested_timeout: int | None = None,
    graph_template: str = "default",
    tools: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> SubagentTask:
    """Create a normalized managed subagent task."""
    max_turns = fallback_max_turns if requested_max_turns is None else requested_max_turns
    default_timeout = _normalize_positive_int(getattr(manager_config, "default_timeout", None)) or 900
    timeout = default_timeout if requested_timeout is None else requested_timeout
    max_turns_limit = _normalize_positive_int(getattr(manager_config, "max_turns_limit", None)) or max_turns
    max_timeout = _normalize_positive_int(getattr(manager_config, "max_timeout", None)) or timeout

    normalized_metadata = {
        str(key): str(value)
        for key, value in (metadata or {}).items()
        if value is not None
    }
    execution_session_id = str(
        normalized_metadata.get("execution_session_id") or ""
    ).strip()
    if not execution_session_id:
        raise ValueError("execution_session_id is required for subagent tasks")
    normalized_metadata["execution_session_id"] = execution_session_id

    return SubagentTask(
        task_id=str(uuid4()),
        thread_id=str(thread_id),
        prompt=prompt,
        created_at=datetime.now(UTC),
        graph_template=graph_template,
        max_turns=max(1, min(max_turns, max_turns_limit)),
        timeout=max(1, min(timeout, max_timeout)),
        tools=[str(tool_name) for tool_name in tools or []],
        metadata=normalized_metadata,
    )
