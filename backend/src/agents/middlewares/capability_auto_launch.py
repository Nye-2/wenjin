"""Deterministic capability launch for explicit user requests."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

_LAUNCH_INTENT_RE = re.compile(
    r"(?:\brun\b|\bexecute\b|\blaunch\b|\bstart\b|执行|启动|开始|跑)",
    re.IGNORECASE,
)


def _configurable(config: RunnableConfig) -> Mapping[str, Any]:
    value = config.get("configurable") if isinstance(config, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _last_user_text(state: ThreadState) -> str:
    for message in reversed(list(state.get("messages") or [])):
        if isinstance(message, HumanMessage):
            return _coerce_text(message.content)
    return ""


def _capability_id_pattern(capability_id: str) -> re.Pattern[str]:
    escaped = re.escape(capability_id)
    return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)


def _match_capability(text: str, capabilities: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not text or not _LAUNCH_INTENT_RE.search(text):
        return None

    for capability in capabilities:
        capability_id = str(capability.get("id") or "").strip()
        if capability_id and _capability_id_pattern(capability_id).search(text):
            return capability

    for capability in capabilities:
        display_name = str(capability.get("display_name") or "").strip()
        if display_name and display_name in text:
            return capability

    return None


def _launch_params(config: RunnableConfig, user_request: str) -> dict[str, Any]:
    configured = _configurable(config).get("launch_feature_params")
    params = dict(configured) if isinstance(configured, Mapping) else {}
    params.setdefault("goal", user_request)
    params.setdefault("user_request", user_request)
    return params


def _reply_text(capability: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    name = str(capability.get("display_name") or capability.get("id") or "能力")
    status = str(result.get("status") or "").strip()
    execution_id = str(result.get("execution_id") or "").strip()
    if status == "launched" and execution_id:
        return f"已启动「{name}」，执行 ID：{execution_id}。"
    detail = str(result.get("detail") or result.get("message") or "").strip()
    if detail:
        return detail
    return f"未能启动「{name}」，请稍后重试。"


async def _invoke_launch_feature(
    *,
    capability_id: str,
    params: dict[str, Any],
    config: RunnableConfig,
) -> Mapping[str, Any]:
    from src.tools.builtins.launch_feature import launch_feature_tool

    result = await launch_feature_tool.ainvoke(
        {
            "feature_id": capability_id,
            "params": params,
        },
        config=config,
    )
    return result if isinstance(result, Mapping) else {"status": "error"}


class CapabilityAutoLaunchMiddleware(Middleware):
    """Call launch_feature directly when the user explicitly names a capability."""

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        capabilities = [
            item
            for item in (state.get("available_capabilities") or [])
            if isinstance(item, dict)
        ]
        capability = _match_capability(_last_user_text(state), capabilities)
        if capability is None:
            return {}

        capability_id = str(capability.get("id") or "").strip()
        user_request = _last_user_text(state)
        params = _launch_params(config, user_request)

        result = await _invoke_launch_feature(
            capability_id=capability_id,
            params=params,
            config=config,
        )
        result_payload = dict(result)
        result_payload.setdefault("feature_id", capability_id)

        call_id = f"auto_launch_{uuid4().hex}"
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "launch_feature",
                        "args": {
                            "feature_id": capability_id,
                            "params": params,
                        },
                        "id": call_id,
                    }
                ],
            ),
            ToolMessage(content=json.dumps(result_payload, ensure_ascii=False), tool_call_id=call_id),
            AIMessage(content=_reply_text(capability, result_payload)),
        ]
        execution_id = result_payload.get("execution_id")
        return {
            "messages": messages,
            "response_metadata": {
                "orchestration": {
                    "feature_id": capability_id,
                    "execution_id": execution_id if isinstance(execution_id, str) else None,
                    "params": params,
                    "status": result_payload.get("status"),
                }
            },
            "_skip_model_call": True,
        }
