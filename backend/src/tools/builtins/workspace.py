"""Workspace-aware tools exposed to the lead agent."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.agents.lead_agent.chat_skill_catalog import get_skill_by_id
from src.agents.lead_agent.feature_bridge_cards import (
    build_confirmation_required_response,
)
from src.agents.thread_state import ThreadState
from src.agents.lead_agent.feature_bridge import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
    execute_workspace_feature_request,
)


class ListWorkspaceFeaturesInput(BaseModel):
    """Input for list_workspace_features."""
    pass


class ListWorkspaceArtifactsInput(BaseModel):
    """Input for list_workspace_artifacts."""

    limit: int = Field(default=8, ge=1, le=20, description="Maximum artifact count to return")


class RunWorkspaceFeatureInput(BaseModel):
    """Input for run_workspace_feature."""

    feature_id: str | None = Field(default=None, description="Workspace feature id to execute")
    skill_id: str | None = Field(
        default=None,
        description="Optional workspace skill id. Must match the feature when provided.",
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Structured feature params")


_CONFIRMATION_ORCHESTRATION_RE = re.compile(
    r"\[orchestration:\s*feature=(?P<feature>[^,\]]+),\s*status=confirmation_required(?:,|\])",
    flags=re.IGNORECASE,
)

_AFFIRMATIVE_PATTERNS = (
    re.compile(r"^(?:好|好的|行|可以|开始|启动|继续|确认)(?:吧|呀|啊|了)?$", re.IGNORECASE),
    re.compile(r"^(?:开始吧|启动吧|继续吧|确认吧)$", re.IGNORECASE),
    re.compile(r"^(?:确认开始|确认启动|可以开始|可以启动|同意启动)$", re.IGNORECASE),
    re.compile(r"^(?:yes|y|ok|okay|go ahead)$", re.IGNORECASE),
)


def _coerce_message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text_parts.append(block["text"].strip())
        return "\n".join(part for part in text_parts if part).strip()
    return str(content or "").strip()


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _runtime_context(config: RunnableConfig | None) -> tuple[str | None, str | None, str | None]:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    if not isinstance(configurable, dict):
        return None, None, None
    return (
        _normalize_optional_str(configurable.get("workspace_id")),
        _normalize_optional_str(configurable.get("thread_id")),
        _normalize_optional_str(configurable.get("user_id")),
    )


def _tool_error_command(
    *,
    tool_call_id: str,
    message: str,
    status: str,
    feature_id: str | None = None,
) -> Command[Any]:
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=message,
                    tool_call_id=tool_call_id,
                )
            ],
            "response_metadata": {
                "orchestration": {
                    "mode": "feature_execution",
                    "feature_id": feature_id,
                    "status": status,
                }
            },
        }
    )


def _resolve_feature_execution_contract(
    *,
    feature_id: str | None,
    skill_id: str | None,
    params: dict[str, Any] | None,
    state: ThreadState | None,
) -> tuple[str | None, str | None, dict[str, Any], str | None]:
    resolved_params = dict(params or {})
    workspace_type = _normalize_optional_str(state.get("workspace_type")) if isinstance(state, dict) else None
    current_skill = _normalize_optional_str(state.get("current_skill")) if isinstance(state, dict) else None
    effective_skill_id = _normalize_optional_str(skill_id) or current_skill
    resolved_feature_id = _normalize_optional_str(feature_id)

    if effective_skill_id and workspace_type:
        skill_def = get_skill_by_id(workspace_type, effective_skill_id)
        if skill_def is None:
            if _normalize_optional_str(skill_id):
                return None, None, resolved_params, f"未知 skill_id: {effective_skill_id}"
        else:
            skill_defaults = dict(skill_def.defaults)
            resolved_params = {**skill_defaults, **resolved_params}
            expected_feature_id = skill_def.feature_id
            if resolved_feature_id is None:
                resolved_feature_id = expected_feature_id
            elif resolved_feature_id != expected_feature_id:
                return (
                    None,
                    None,
                    resolved_params,
                    f"当前 skill `{effective_skill_id}` 只能执行 `{expected_feature_id}`，"
                    f"不能执行 `{resolved_feature_id}`。",
                )
            return resolved_feature_id, skill_def.id, resolved_params, None

    if resolved_feature_id is None:
        return None, None, resolved_params, "缺少 feature_id，且当前没有可推断的 skill 上下文。"
    return resolved_feature_id, None, resolved_params, None


def _latest_user_message_text(state: ThreadState) -> str | None:
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", None) in {"human", "user"}:
            text = _coerce_message_text(message)
            if text:
                return text
    return None


def _latest_pending_confirmation_feature(state: ThreadState) -> str | None:
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", None) not in {"ai", "assistant"}:
            continue
        content = _coerce_message_text(message)
        if not content:
            continue
        match = _CONFIRMATION_ORCHESTRATION_RE.search(content)
        if match:
            feature_id = str(match.group("feature") or "").strip()
            return feature_id or None
    return None


def _message_is_affirmative_confirmation(message: str | None) -> bool:
    normalized = " ".join(str(message or "").strip().split()).lower().rstrip("。！？!?")
    if not normalized:
        return False
    return any(pattern.match(normalized) for pattern in _AFFIRMATIVE_PATTERNS)


def _state_has_pending_confirmation(
    *,
    state: ThreadState,
    feature_id: str,
) -> bool:
    """Check whether this turn already produced a confirmation-required response."""
    response_metadata = state.get("response_metadata")
    if not isinstance(response_metadata, dict):
        return False
    orchestration = response_metadata.get("orchestration")
    if not isinstance(orchestration, dict):
        return False
    pending_feature = str(orchestration.get("feature_id") or "").strip()
    status = str(orchestration.get("status") or "").strip().lower()
    if pending_feature != feature_id:
        return False
    return status in {"confirmation_required", "awaiting_user_confirmation"}


def _is_feature_execution_confirmed(
    *,
    state: ThreadState,
    feature_id: str,
) -> bool:
    pending_feature = _latest_pending_confirmation_feature(state)
    if pending_feature != feature_id:
        return False
    latest_user_message = _latest_user_message_text(state)
    return _message_is_affirmative_confirmation(latest_user_message)


def _confirmation_command(
    *,
    tool_call_id: str,
    feature_id: str,
    params: dict[str, Any] | None = None,
) -> Command[Any]:
    reply = build_confirmation_required_response(
        feature_id=feature_id,
        params=params,
    )
    update: dict[str, Any] = {
        "messages": [
            ToolMessage(
                content=reply.content,
                tool_call_id=tool_call_id,
            )
        ]
    }
    if reply.blocks:
        update["response_blocks"] = reply.blocks
    if reply.metadata:
        update["response_metadata"] = reply.metadata
    return Command(update=update)


def _awaiting_confirmation_command(
    *,
    tool_call_id: str,
    feature_id: str,
) -> Command[Any]:
    """Return a stable response when confirmation is still pending in the same turn."""
    content = (
        "该功能仍在等待你的确认。"
        " 请直接回复“开始吧”或“确认启动”，我就立即执行；"
        " 若暂不执行，请告诉我你想先做的分析。"
    )
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                )
            ],
            "response_metadata": {
                "orchestration": {
                    "mode": "feature_execution",
                    "feature_id": feature_id,
                    "status": "awaiting_user_confirmation",
                }
            },
        }
    )


@tool("list_workspace_features", args_schema=ListWorkspaceFeaturesInput)
async def list_workspace_features_tool(
    config: RunnableConfig | None = None,
) -> str:
    """List available workspace features for the current workspace."""
    workspace_id, _, user_id = _runtime_context(config)
    if workspace_id is None or user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)
    overview = await build_workspace_feature_overview(workspace_id, user_id=user_id)
    if overview is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(overview, ensure_ascii=False)


@tool("list_workspace_artifacts", args_schema=ListWorkspaceArtifactsInput)
async def list_workspace_artifacts_tool(
    limit: int = 8,
    config: RunnableConfig | None = None,
) -> str:
    """List recent artifacts produced inside the current workspace."""
    workspace_id, _, user_id = _runtime_context(config)
    if workspace_id is None or user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)
    artifacts = await build_workspace_artifact_overview(
        workspace_id,
        user_id=user_id,
        limit=limit,
    )
    if artifacts is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(
        {"workspace_id": workspace_id, "count": len(artifacts), "artifacts": artifacts},
        ensure_ascii=False,
    )


@tool("run_workspace_feature", args_schema=RunWorkspaceFeatureInput)
async def run_workspace_feature_tool(
    feature_id: str | None = None,
    skill_id: str | None = None,
    params: dict[str, Any] | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> Command[Any]:
    """Run a canonical workspace feature and return structured execution metadata."""
    workspace_id, thread_id, user_id = _runtime_context(config)
    if workspace_id is None or thread_id is None or user_id is None:
        return _tool_error_command(
            tool_call_id=tool_call_id,
            message="当前运行时缺少 workspace/thread/user 上下文，无法执行该功能。",
            status="runtime_context_missing",
            feature_id=feature_id,
        )

    resolved_feature_id, resolved_skill_id, resolved_params, contract_error = (
        _resolve_feature_execution_contract(
            feature_id=feature_id,
            skill_id=skill_id,
            params=params,
            state=state,
        )
    )
    if contract_error:
        return _tool_error_command(
            tool_call_id=tool_call_id,
            message=contract_error,
            status="skill_contract_error",
            feature_id=resolved_feature_id or feature_id,
        )

    if state is not None and _state_has_pending_confirmation(
        state=state,
        feature_id=str(resolved_feature_id),
    ):
        latest_user_message = _latest_user_message_text(state)
        if not _message_is_affirmative_confirmation(latest_user_message):
            return _awaiting_confirmation_command(
                tool_call_id=tool_call_id,
                feature_id=str(resolved_feature_id),
            )

    if state is None or not _is_feature_execution_confirmed(
        state=state,
        feature_id=str(resolved_feature_id),
    ):
        return _confirmation_command(
            tool_call_id=tool_call_id,
            feature_id=str(resolved_feature_id),
            params=resolved_params,
        )

    reply = await execute_workspace_feature_request(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
        feature_id=str(resolved_feature_id),
        params=resolved_params,
        skill_id=resolved_skill_id,
    )
    if reply is None:
        payload = json.dumps(
            {
                "error": "feature_execution_unavailable",
                "feature_id": resolved_feature_id,
            },
            ensure_ascii=False,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=payload,
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    update: dict[str, Any] = {
        "messages": [
            ToolMessage(
                content=reply.content,
                tool_call_id=tool_call_id,
            )
        ]
    }
    if reply.blocks:
        update["response_blocks"] = reply.blocks
    if reply.metadata:
        update["response_metadata"] = reply.metadata

    return Command(update=update)
