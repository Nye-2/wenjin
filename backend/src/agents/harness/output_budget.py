"""Output bounding helpers for harness tools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from src.sandbox.workspace_layout import WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT

HARNESS_OUTPUTS_ROOT = WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT
DEFAULT_EXTERNALIZE_ABOVE_CHARS = 12_000
DEFAULT_PREVIEW_HEAD_CHARS = 4_000
DEFAULT_PREVIEW_TAIL_CHARS = 2_000
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class BudgetedText:
    """Bounded model-visible text plus optional full-output references."""

    preview_text: str
    output_refs: tuple[str, ...] = ()
    truncated: bool = False
    externalized: bool = False


def cap_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Return a bounded text preview and whether it was truncated."""

    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def select_lines(
    content: str,
    *,
    start_line: int | None,
    end_line: int | None,
) -> str:
    """Return a 1-based inclusive line window from content."""

    if start_line is None and end_line is None:
        return content
    lines = content.splitlines(keepends=True)
    start = max((start_line or 1) - 1, 0)
    end = min(end_line or len(lines), len(lines))
    return "".join(lines[start:end])


async def budget_text_output(
    *,
    text: str,
    tool_name: str,
    context: Any,
    sandbox: Any,
    output_budget: dict[str, Any],
    fallback_max_chars: int,
    extension: str = "txt",
) -> BudgetedText:
    """Externalize oversized text output, otherwise return a bounded preview.

    The full output is written under `/workspace/outputs/harness/...` so it
    stays inside the workspace sandbox contract and can be read by follow-up
    sandbox tools. If persistence fails, the caller still receives a bounded
    preview instead of unbounded text.
    """

    if fallback_max_chars < 0:
        raise ValueError("fallback_max_chars must be non-negative")

    threshold = int(output_budget.get("externalize_above_chars") or DEFAULT_EXTERNALIZE_ABOVE_CHARS)
    if threshold > 0 and len(text) > threshold:
        output_ref = harness_output_path(
            context=context,
            tool_name=tool_name,
            extension=extension,
            content_fingerprint=_content_fingerprint(text),
        )
        try:
            await sandbox.write_file(output_ref, text)
        except Exception:
            preview, truncated = cap_text(text, fallback_max_chars)
            return BudgetedText(preview_text=preview, truncated=truncated, externalized=False)

        preview = externalized_preview(
            text,
            tool_name=tool_name,
            output_ref=output_ref,
            head_chars=int(output_budget.get("preview_head_chars") or DEFAULT_PREVIEW_HEAD_CHARS),
            tail_chars=int(output_budget.get("preview_tail_chars") or DEFAULT_PREVIEW_TAIL_CHARS),
        )
        return BudgetedText(
            preview_text=preview,
            output_refs=(output_ref,),
            truncated=True,
            externalized=True,
        )

    preview, truncated = cap_text(text, fallback_max_chars)
    return BudgetedText(preview_text=preview, truncated=truncated, externalized=False)


def harness_output_path(
    *,
    context: Any,
    tool_name: str,
    extension: str = "txt",
    content_fingerprint: str | None = None,
) -> str:
    """Return a deterministic workspace path for one harness tool output."""

    safe_extension = _safe_segment(extension.strip().lstrip("."), "txt")
    safe_tool_name = _safe_segment(tool_name, "tool")
    suffix = f"-{_safe_segment(content_fingerprint, 'output')}" if content_fingerprint else ""
    return "/".join(
        (
            HARNESS_OUTPUTS_ROOT,
            _safe_segment(getattr(context, "execution_id", None), "execution"),
            _safe_segment(getattr(context, "node_id", None), "node"),
            _safe_segment(getattr(context, "invocation_id", None), "invocation"),
            f"{safe_tool_name}{suffix}.{safe_extension}",
        )
    )


def externalized_preview(
    text: str,
    *,
    tool_name: str,
    output_ref: str,
    head_chars: int,
    tail_chars: int,
) -> str:
    """Build a compact head/tail preview with a full-output reference."""

    total = len(text)
    total_lines = text.count("\n") + (0 if not text or text.endswith("\n") else 1)
    head_end = _snap_to_line_boundary(text, min(max(head_chars, 0), total))
    tail_start = max(head_end, total - max(tail_chars, 0))
    snapped_tail = _snap_to_line_boundary(text, tail_start)
    if snapped_tail > head_end:
        tail_start = snapped_tail

    head = text[:head_end]
    tail = text[tail_start:] if tail_start < total else ""
    omitted = max(total - len(head) - len(tail), 0)
    ref = (
        f"\n\n[Full {tool_name} output saved to {output_ref} "
        f"({total} chars, {total_lines} lines). "
        f"Use sandbox.read_file with start_line/end_line to inspect details. "
        f"{omitted} chars omitted from this preview.]\n\n"
    )
    return "".join((f"Total output lines: {total_lines}\n\n", head, ref, tail))


def _safe_segment(value: Any, default: str) -> str:
    text = str(value or "").strip()
    text = _SAFE_SEGMENT_RE.sub("-", text).strip(".-")
    return (text or default)[:100]


def _content_fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:12]


def _snap_to_line_boundary(text: str, pos: int) -> int:
    if pos <= 0 or pos >= len(text):
        return pos
    half = pos // 2
    newline = text.rfind("\n", half, pos)
    return newline + 1 if newline >= 0 else pos
