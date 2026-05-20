"""Canonical conversation block protocol helpers."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Any


class ConversationBlockKind(enum.StrEnum):
    """Canonical block kinds stored by DataService."""

    TEXT = "text"
    THINKING = "thinking"
    STATUS_LINE = "status_line"
    QUESTION_CARD = "question_card"
    RESULT_CARD = "result_card"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"


CANONICAL_BLOCK_KINDS = tuple(kind.value for kind in ConversationBlockKind)

_BLOCK_KIND_ALIASES = {
    "reasoning": ConversationBlockKind.THINKING.value,
    "thought": ConversationBlockKind.THINKING.value,
    "tool": ConversationBlockKind.TOOL_INVOCATION.value,
    "tool_call": ConversationBlockKind.TOOL_INVOCATION.value,
    "tool_use": ConversationBlockKind.TOOL_INVOCATION.value,
}


def canonical_block_kind(block: Mapping[str, Any]) -> str:
    """Return the canonical block kind for a persisted block payload."""
    raw_kind = str(block.get("kind") or block.get("type") or "").strip()
    if raw_kind in CANONICAL_BLOCK_KINDS:
        return raw_kind
    return _BLOCK_KIND_ALIASES.get(raw_kind, ConversationBlockKind.TEXT.value)


def normalize_block_payload(
    block: Mapping[str, Any],
    *,
    default_text: str | None = None,
) -> dict[str, Any]:
    """Return a JSON payload with canonical ``kind`` while preserving raw fields."""
    payload = dict(block)
    kind = canonical_block_kind(payload)
    previous_kind = payload.get("kind") or payload.get("type")
    payload["kind"] = kind
    payload.pop("type", None)
    if previous_kind and str(previous_kind) != kind:
        payload.setdefault("legacy_kind", str(previous_kind))
    if kind == ConversationBlockKind.TEXT.value and "content" not in payload and default_text:
        payload["content"] = default_text
    return payload


def blocks_from_message(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract ordered canonical blocks from a persisted message payload."""
    raw_blocks = message.get("blocks")
    if isinstance(raw_blocks, list):
        blocks = [
            normalize_block_payload(block)
            for block in raw_blocks
            if isinstance(block, Mapping)
        ]
        if blocks:
            return blocks

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return [
            normalize_block_payload(
                {"kind": ConversationBlockKind.TEXT.value, "content": content},
                default_text=content,
            )
        ]
    return []


def extract_tool_name(payload: Mapping[str, Any]) -> str | None:
    """Best-effort tool name extraction from tool block payloads."""
    for key in ("tool_name", "name", "tool", "function_name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    function = payload.get("function")
    if isinstance(function, Mapping):
        name = function.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def extract_tool_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort input extraction from a tool invocation block."""
    for key in ("input", "args", "arguments", "parameters"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def extract_tool_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort output extraction from a tool result block."""
    for key in ("output", "result", "data"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
        if value is not None:
            return {"value": value}
    return {}


def extract_invocation_ref(payload: Mapping[str, Any]) -> str | None:
    """Best-effort invocation correlation id extraction."""
    for key in ("invocation_id", "tool_call_id", "call_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
