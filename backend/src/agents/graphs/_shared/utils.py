"""Shared utilities for LangGraph sub-graphs.

Common functions:
- JSON parsing (from thesis patterns)
- Model creation with safety
- Generation mode detection
- Text and parameter normalization
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Parsing Utilities
# ---------------------------------------------------------------------------


def _strip_markdown_fence(text: str) -> str:
    """Strip markdown code fences from text if present.

    Handles both ```lang\\n...\\n``` and ```\\n...\\n``` formats.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.split("\n")
    if len(lines) < 2:
        return text

    # Remove opening fence (with optional language tag)
    # Remove closing fence if present
    if lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return "\n".join(lines[1:])


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown fences.

    Args:
        text: Raw LLM response text

    Returns:
        Parsed dict or None if parsing fails
    """
    try:
        cleaned = _strip_markdown_fence(text)
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        logger.debug("JSON parsing failed")
        return None
    except Exception:
        logger.exception("parse_json_response error")
        return None


def parse_json_list_response(text: str) -> list[dict[str, Any]] | None:
    """Parse JSON list from LLM response, handling markdown fences.

    Args:
        text: Raw LLM response text

    Returns:
        Parsed list of dicts or None if parsing fails
    """
    try:
        cleaned = _strip_markdown_fence(text)
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            # Validate all items are dicts
            if all(isinstance(item, dict) for item in parsed):
                return parsed
        return None
    except json.JSONDecodeError:
        logger.debug("JSON list parsing failed")
        return None
    except Exception:
        logger.exception("parse_json_list_response error")
        return None


# ---------------------------------------------------------------------------
# Model Creation Utilities
# ---------------------------------------------------------------------------


async def create_model_safe(
    model_id: str | None = None,
    temperature: float = 0.3,
) -> Any:
    """Safely create a chat model with error handling.

    Args:
        model_id: Optional model ID to use
        temperature: Temperature for generation (0.0-1.0)

    Returns:
        Chat model instance or None if creation fails
    """
    try:
        from src.models.factory import create_chat_model

        return create_chat_model(model_id, temperature=temperature)
    except Exception:
        logger.exception("Failed to create chat model")
        return None


# ---------------------------------------------------------------------------
# Generation Mode Detection
# ---------------------------------------------------------------------------


def detect_generation_mode(step_results: dict[str, bool]) -> str:
    """Determine overall generation mode from step results.

    Args:
        step_results: Dict mapping step name -> succeeded status
            Example: {"phase2_llm": True, "phase3_validation": False}

    Returns:
        "llm" if all succeeded, "partial_llm" if some succeeded, "failed" if all failed
    """
    if not step_results:
        return "failed"

    succeeded = sum(1 for v in step_results.values() if v)
    total = len(step_results)

    if succeeded == total:
        return "llm"
    if succeeded > 0:
        return "partial_llm"
    return "failed"


# ---------------------------------------------------------------------------
# Parameter Normalization Utilities
# ---------------------------------------------------------------------------


def build_memory_context_text(memory_context: str | None) -> str:
    """Build memory context text for LLM prompts.

    Args:
        memory_context: Optional memory context string

    Returns:
        Formatted memory context string or empty string
    """
    if memory_context:
        return f"\n用户记忆上下文:\n{memory_context}"
    return ""


def _utc_now_iso() -> str:
    """Return current UTC time as ISO format string.

    Returns:
        ISO formatted timestamp string (e.g., "2026-03-18T12:34:56.789012+00:00")
    """
    return datetime.now(tz=UTC).isoformat()


def _normalize_list(value: Any, *, max_items: int = 10) -> list[str]:
    """Normalize params values into a non-empty string list.

    Handles comma-separated strings and lists, with optional item limit.

    Args:
        value: Input value (string, list, or other)
        max_items: Maximum number of items to return (default 10)

    Returns:
        List of non-empty stripped strings, limited to max_items
    """
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        result = [item for item in parts if item]
    elif isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
    else:
        return []

    return result[:max_items]


def _read_optional_str(value: Any) -> str | None:
    """Read optional string value, returning None for empty/whitespace strings.

    Args:
        value: Input value of any type

    Returns:
        Stripped string if non-empty, None otherwise
    """
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _read_optional_int(value: Any) -> int | None:
    """Read optional int value, returning None for invalid/missing values.

    Args:
        value: Input value of any type

    Returns:
        Integer value if valid, None otherwise
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_payload_params(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Read nested business params from a task payload.

    Workspace feature task payloads keep orchestration metadata at the top level
    and all user/business inputs under ``params``.
    """
    if not isinstance(payload, dict):
        return {}
    params = payload.get("params")
    return params if isinstance(params, dict) else {}


def _normalize_text(value: Any, fallback: str = "") -> str:
    """Normalize text value with fallback.

    Args:
        value: Input value of any type
        fallback: Default string to return if value is empty/None

    Returns:
        Stripped string if non-empty, fallback otherwise
    """
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback
