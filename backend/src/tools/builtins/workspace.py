"""Workspace-aware tools exposed to the lead agent."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

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

    workspace_id: str = Field(description="Current workspace id")


class ListWorkspaceArtifactsInput(BaseModel):
    """Input for list_workspace_artifacts."""

    workspace_id: str = Field(description="Current workspace id")
    limit: int = Field(default=8, ge=1, le=20, description="Maximum artifact count to return")


class RunWorkspaceFeatureInput(BaseModel):
    """Input for run_workspace_feature."""

    workspace_id: str = Field(description="Current workspace id")
    thread_id: str = Field(description="Current chat thread id")
    user_id: str = Field(description="Current authenticated user id")
    feature_id: str = Field(description="Workspace feature id to execute")
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
async def list_workspace_features_tool(workspace_id: str) -> str:
    """List available workspace features for the current workspace."""
    overview = await build_workspace_feature_overview(workspace_id)
    if overview is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(overview, ensure_ascii=False)


@tool("list_workspace_artifacts", args_schema=ListWorkspaceArtifactsInput)
async def list_workspace_artifacts_tool(workspace_id: str, limit: int = 8) -> str:
    """List recent artifacts produced inside the current workspace."""
    artifacts = await build_workspace_artifact_overview(workspace_id, limit=limit)
    return json.dumps(
        {"workspace_id": workspace_id, "count": len(artifacts), "artifacts": artifacts},
        ensure_ascii=False,
    )


@tool("run_workspace_feature", args_schema=RunWorkspaceFeatureInput)
async def run_workspace_feature_tool(
    workspace_id: str,
    thread_id: str,
    user_id: str,
    feature_id: str,
    params: dict[str, Any] | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[ThreadState, InjectedState] | None = None,
) -> Command[Any]:
    """Run a canonical workspace feature and return structured execution metadata."""
    if state is not None and _state_has_pending_confirmation(
        state=state,
        feature_id=feature_id,
    ):
        latest_user_message = _latest_user_message_text(state)
        if not _message_is_affirmative_confirmation(latest_user_message):
            return _awaiting_confirmation_command(
                tool_call_id=tool_call_id,
                feature_id=feature_id,
            )

    if state is None or not _is_feature_execution_confirmed(
        state=state,
        feature_id=feature_id,
    ):
        return _confirmation_command(
            tool_call_id=tool_call_id,
            feature_id=feature_id,
            params=params,
        )

    reply = await execute_workspace_feature_request(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
        feature_id=feature_id,
        params=params,
    )
    if reply is None:
        payload = json.dumps(
            {
                "error": "feature_execution_unavailable",
                "feature_id": feature_id,
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
