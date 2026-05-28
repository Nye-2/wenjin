"""Prism-focused deterministic subagents."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from src.services.latex.feedback_revision_service import rewrite_with_feedback

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent


def _read_text_input(inputs: dict[str, Any], key: str) -> str:
    value = inputs.get(key)
    return str(value or "").strip()


def _read_optional_int(inputs: dict[str, Any], key: str) -> int | None:
    value = inputs.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_slice(text: str, limit: int = 160) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


@subagent("prism_selection_optimizer")
class PrismSelectionOptimizerSubagent(SubagentBase):
    """Rewrite a Prism selection and stage it as a reviewable file change."""

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        inputs = dict(ctx.inputs or {})
        file_path = _read_text_input(inputs, "file_path")
        file_content = str(inputs.get("file_content") or "")
        selected_text = str(inputs.get("selected_text") or "")
        instruction = _read_text_input(inputs, "instruction") or _read_text_input(inputs, "comment")
        feedback_id = _read_text_input(inputs, "feedback_id")
        scope = _read_text_input(inputs, "scope") or "section"
        if scope not in {"selection", "section"}:
            scope = "section"

        if not file_path:
            raise ValueError("Prism selection optimization requires file_path")
        if not file_content:
            raise ValueError("Prism selection optimization requires current file_content")
        if not selected_text.strip():
            raise ValueError("Prism selection optimization requires selected_text")
        if not instruction:
            raise ValueError("Prism selection optimization requires instruction/comment")

        selection_start = _read_optional_int(inputs, "selection_start")
        selection_end = _read_optional_int(inputs, "selection_end")
        anchor = inputs.get("anchor") if isinstance(inputs.get("anchor"), dict) else None

        await ctx.emit("thinking", "正在定位 Prism 选区并读取上下文。")
        rewrite_result = await rewrite_with_feedback(
            content=file_content,
            comment=instruction,
            selected_text=selected_text,
            selection_start=selection_start,
            selection_end=selection_end,
            anchor=anchor,
            scope=scope,  # type: ignore[arg-type]
            requested_model_id=_read_text_input(inputs, "model_id") or None,
        )

        target_start = int(rewrite_result["target_start"])
        target_end = int(rewrite_result["target_end"])
        rewritten_text = str(rewrite_result["rewritten_text"])
        if target_start < 0 or target_end < target_start or target_end > len(file_content):
            raise ValueError("Prism rewrite target range is invalid for current file")

        pending_content = (
            file_content[:target_start]
            + rewritten_text
            + file_content[target_end:]
        )
        current_hash = sha256(file_content.encode("utf-8")).hexdigest()
        pending_hash = sha256(pending_content.encode("utf-8")).hexdigest()
        section_title = str(rewrite_result.get("section_title") or "").strip()
        changes_summary = str(rewrite_result.get("changes_summary") or "").strip()
        logical_seed = feedback_id or f"{file_path}:{selection_start}:{selection_end}:{current_hash[:12]}"
        logical_key = f"prism_selection_optimize:{logical_seed}"

        await ctx.emit("thinking", "已生成局部优化候选，正在写入 Prism 待审阅变更。")
        output = {
            "path": file_path,
            "pending_content": pending_content,
            "content_format": "raw",
            "logical_key": logical_key,
            "reason": changes_summary or f"Prism 划词优化：{section_title or file_path}",
            "current_hash": current_hash,
            "pending_hash": pending_hash,
            "scope": rewrite_result.get("scope") or scope,
            "section_title": section_title,
            "section_level": rewrite_result.get("section_level") or "",
            "resolved_selection_start": rewrite_result.get("resolved_selection_start"),
            "resolved_selection_end": rewrite_result.get("resolved_selection_end"),
            "target_start": target_start,
            "target_end": target_end,
            "rewritten_text": rewritten_text,
            "changes_summary": changes_summary,
            "selected_text_preview": _safe_slice(selected_text),
        }
        return SubagentResult(
            output=output,
            thinking="Generated a reviewable Prism file-change candidate from the selected manuscript text.",
            tool_calls=[
                {
                    "name": "prism.feedback_rewrite",
                    "args": {
                        "file_path": file_path,
                        "scope": scope,
                        "selection_start": selection_start,
                        "selection_end": selection_end,
                    },
                    "status": "completed",
                }
            ],
            token_usage=None,
        )
