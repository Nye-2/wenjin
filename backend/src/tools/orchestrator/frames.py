"""Strict provider tool-frame decoding.

Assistant content is deliberately ignored. JSON, XML, Markdown, or a tool name
inside prose can never become an executable call.
"""

from __future__ import annotations

import json
from typing import Any

from src.tools.orchestrator.contracts import ProviderToolCall
from src.tools.orchestrator.errors import MalformedToolArgumentsError


def parse_chat_completions_tool_calls(response: dict[str, Any]) -> tuple[ProviderToolCall, ...]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise MalformedToolArgumentsError("provider response has no structured choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise MalformedToolArgumentsError("provider response has no structured message")
    return parse_tool_call_items(message.get("tool_calls"))


def parse_tool_call_items(value: Any) -> tuple[ProviderToolCall, ...]:
    if not isinstance(value, list) or not value:
        raise MalformedToolArgumentsError("provider response has no structured tool call")
    calls: list[ProviderToolCall] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "function":
            raise MalformedToolArgumentsError("unsupported provider tool-call frame")
        function = item.get("function")
        if not isinstance(function, dict):
            raise MalformedToolArgumentsError("tool-call function frame is missing")
        call_id = str(item.get("id") or "").strip()
        tool_id = str(function.get("name") or "").strip()
        raw_arguments = function.get("arguments")
        if not call_id or not tool_id or not isinstance(raw_arguments, str):
            raise MalformedToolArgumentsError("tool-call identity or arguments are malformed")
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise MalformedToolArgumentsError("tool-call arguments are not valid JSON") from exc
        if not isinstance(arguments, dict):
            raise MalformedToolArgumentsError("tool-call arguments must be a JSON object")
        calls.append(
            ProviderToolCall(
                call_id=call_id,
                tool_id=tool_id,
                arguments=arguments,
            )
        )
    return tuple(calls)


__all__ = ["parse_chat_completions_tool_calls", "parse_tool_call_items"]
