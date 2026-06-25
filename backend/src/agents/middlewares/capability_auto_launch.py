"""Deterministic capability launch for explicit user requests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


def _configurable(config: RunnableConfig | None) -> dict[str, Any]:
    raw = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    return raw if isinstance(raw, dict) else {}


def _is_hidden_capability(capability: Mapping[str, Any]) -> bool:
    display = capability.get("display")
    display = display if isinstance(display, Mapping) else {}
    definition = capability.get("definition_json")
    definition = definition if isinstance(definition, Mapping) else {}
    definition_display = definition.get("display")
    definition_display = definition_display if isinstance(definition_display, Mapping) else {}
    tiers = (
        capability.get("entry_tier"),
        capability.get("tier"),
        display.get("entry_tier"),
        display.get("tier"),
        definition_display.get("entry_tier"),
        definition_display.get("tier"),
    )
    return any(str(tier or "").strip().lower() == "hidden" for tier in tiers)


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
    """Call launch_feature directly only for explicit runtime entry metadata."""

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        configurable = _configurable(config)
        explicit_feature_id = str(configurable.get("launch_feature_id") or "").strip()
        if not explicit_feature_id:
            return {}

        capabilities = [
            item
            for item in (state.get("available_capabilities") or [])
            if isinstance(item, dict)
        ]
        capability = next(
            (
                item
                for item in capabilities
                if str(item.get("id") or "").strip() == explicit_feature_id
                and not _is_hidden_capability(item)
            ),
            None,
        )
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
