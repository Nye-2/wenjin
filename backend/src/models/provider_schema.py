"""Strict provider-tool schema helpers shared by model boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


class ProviderToolPayloadError(ValueError):
    """Raised when a provider JSON-text field is not a JSON object."""


def strict_provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize Pydantic JSON Schema to the provider strict-tools contract."""
    normalized = deepcopy(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(normalized)
    return normalized


def parse_json_object(value: str, *, field_name: str) -> dict[str, Any]:
    """Decode a strict wire string while preserving an open internal object."""
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProviderToolPayloadError(f"{field_name} must contain valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ProviderToolPayloadError(f"{field_name} must contain a JSON object")
    return decoded


__all__ = ["ProviderToolPayloadError", "parse_json_object", "strict_provider_schema"]
