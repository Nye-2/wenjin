"""Capability YAML template renderer.

Capability seeds describe task inputs and output mappings with Jinja-style
``{{path}}`` expressions::

    inputs:
      query: "{{topic}}"
      year_min: "{{year_min|default(2019)}}"
      papers: "{{phases.discover.search.output.papers}}"

This module renders those expressions against a runtime context.  We do *not*
pull in full Jinja2 — only the small subset capability seeds actually use:

  * Pure templates  — ``"{{foo.bar}}"``.  Whole-string template, returns the
    resolved value with its native type (so list / dict references survive).
  * Interpolated strings — ``"prefix {{x}} suffix"``.  Each ``{{...}}`` segment
    is replaced with ``str(value)``; missing values render as empty strings.
  * ``default(value)`` filter — single supported filter,
    ``{{x|default(literal)}}``.  Literal supports ints, floats, strings (single
    or double quoted), booleans, and ``null``.

Anything else falls back to ``None`` — callers can layer additional filters
later if a capability seed requires them.
"""

from __future__ import annotations

import re
from typing import Any

_TEMPLATE_PATTERN = re.compile(r"\{\{(.+?)\}\}")
_DEFAULT_FILTER_PATTERN = re.compile(r"^\s*default\s*\(\s*(.+?)\s*\)\s*$")
_MAX_RENDER_CONTEXT_STRING = 700
_MAX_RENDER_CONTEXT_LIST = 16
_DROP_RENDER_CONTEXT_KEYS = frozenset(
    {
        "metadata",
        "metadata_json",
        "raw",
        "raw_json",
        "full_text",
    }
)


def _is_pure_template(value: str) -> bool:
    """True iff the whole string is exactly one ``{{...}}`` (no surrounding text)."""
    stripped = value.strip()
    return (
        stripped.startswith("{{")
        and stripped.endswith("}}")
        and stripped.count("{{") == 1
        and stripped.count("}}") == 1
    )


def _parse_literal(text: str) -> Any:
    """Parse a Python-ish literal used inside ``default(...)``."""
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text in {"null", "None"}:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _resolve_path(ctx: Any, path: str) -> Any:
    """Walk a dot-separated path against a dict-like context.

    Returns ``None`` on any miss (missing key, non-dict node).
    """
    current: Any = ctx
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current


def _resolve_expr(inner: str, ctx: dict[str, Any]) -> Any:
    """Resolve the contents of a single ``{{...}}`` expression."""
    inner = inner.strip()

    # Split off filter if present
    filter_part: str | None = None
    if "|" in inner:
        path_part, _, filter_part = inner.partition("|")
        inner = path_part.strip()
        filter_part = filter_part.strip()

    value = _resolve_path(ctx, inner)

    if value is None and filter_part:
        match = _DEFAULT_FILTER_PATTERN.match(filter_part)
        if match:
            return _parse_literal(match.group(1))

    return value


def render_template(value: Any, ctx: dict[str, Any]) -> Any:
    """Recursively render templates inside ``value`` against ``ctx``.

    Behaviour matrix:
        ``"{{x}}"``               → ``ctx["x"]`` (native type preserved)
        ``"{{x|default(1)}}"``    → ``1`` when ``x`` is missing
        ``"a {{x}} b"``           → ``"a <str(x)> b"`` (missing → "")
        plain string              → returned unchanged
        dict / list               → walked recursively, values rendered in place
        non-string scalar         → returned unchanged
    """
    if isinstance(value, str):
        if _is_pure_template(value):
            inner = value.strip()[2:-2]
            return _resolve_expr(inner, ctx)
        if "{{" in value:
            def _replace(match: re.Match[str]) -> str:
                resolved = _resolve_expr(match.group(1), ctx)
                return "" if resolved is None else str(resolved)
            return _TEMPLATE_PATTERN.sub(_replace, value)
        return value

    if isinstance(value, dict):
        return {key: render_template(sub, ctx) for key, sub in value.items()}

    if isinstance(value, list):
        return [render_template(sub, ctx) for sub in value]

    return value


def _compact_string_for_render(value: str) -> str:
    if len(value) <= _MAX_RENDER_CONTEXT_STRING:
        return value
    return value[: _MAX_RENDER_CONTEXT_STRING - 1].rstrip() + "…"


def _compact_node_result_for_render(value: Any) -> Any:
    """Bound upstream context before it is injected into downstream LLM inputs."""
    if isinstance(value, str):
        return _compact_string_for_render(value)

    if isinstance(value, list):
        return [
            _compact_node_result_for_render(item)
            for item in value[:_MAX_RENDER_CONTEXT_LIST]
        ]

    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in _DROP_RENDER_CONTEXT_KEYS:
                continue
            compacted[key] = _compact_node_result_for_render(item)
        return compacted

    return value


def build_task_render_context(
    *,
    brief: dict[str, Any],
    node_results: dict[str, Any],
    phase_index: dict[str, list[str]],
) -> dict[str, Any]:
    """Build the rendering context a single task sees at run time.

    Top-level keys come from ``brief`` (so ``{{topic}}`` works directly).  A
    nested ``phases.<phase>.<task>`` namespace exposes upstream results so
    expressions like ``{{phases.discover.search.output.papers}}`` resolve to
    the actual searcher output once that node has completed.
    """
    ctx: dict[str, Any] = dict(brief or {})
    phases_ctx: dict[str, dict[str, Any]] = {}
    for phase_name, task_names in phase_index.items():
        bucket: dict[str, Any] = {}
        for task_name in task_names:
            entry = node_results.get(task_name)
            if isinstance(entry, dict):
                bucket[task_name] = _compact_node_result_for_render(entry)
        phases_ctx[phase_name] = bucket
    ctx["phases"] = phases_ctx
    return ctx
