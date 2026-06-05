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


def _read_context_requirements(inputs: dict[str, Any]) -> dict[str, bool]:
    raw = inputs.get("context_requirements")
    if not isinstance(raw, dict):
        return {}
    return {
        "include_workspace_history": bool(raw.get("include_workspace_history")),
        "include_related_documents": bool(raw.get("include_related_documents")),
        "include_sandbox_artifacts": bool(raw.get("include_sandbox_artifacts")),
    }


def _append_workspace_context_instruction(
    instruction: str,
    *,
    inputs: dict[str, Any],
    workspace_data: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    rewrite_mode = _read_text_input(inputs, "rewrite_mode")
    context_strategy = _read_text_input(inputs, "context_strategy")
    requirements = _read_context_requirements(inputs)
    if rewrite_mode != "document" and context_strategy != "workspace_manuscript_review":
        return instruction, {}

    lines: list[str] = []
    usage = {
        "related_documents": 0,
        "decisions": 0,
        "memory": 0,
        "recent_executions": 0,
        "sandbox_artifacts": 0,
    }

    if requirements.get("include_related_documents"):
        documents = workspace_data.get("related_documents")
        if not isinstance(documents, list):
            library_context = workspace_data.get("library_context")
            documents = (
                library_context.get("citable_sources", [])
                if isinstance(library_context, dict)
                else []
            )
        if documents:
            lines.append("相关文献/材料摘要：")
            for item in documents[:8]:
                if not isinstance(item, dict):
                    continue
                usage["related_documents"] += 1
                title = _safe_slice(str(item.get("title") or "未命名材料"), 90)
                citation_key = str(item.get("citation_key") or "").strip()
                abstract = _safe_slice(str(item.get("abstract_excerpt") or ""), 160)
                suffix = f"；摘要：{abstract}" if abstract else ""
                key = f" [{citation_key}]" if citation_key else ""
                lines.append(f"- {title}{key}{suffix}")

    if requirements.get("include_workspace_history"):
        history = workspace_data.get("workspace_history")
        if isinstance(history, dict):
            decisions = history.get("decisions")
            if isinstance(decisions, list) and decisions:
                lines.append("工作区已确认决策：")
                for item in decisions[:8]:
                    if not isinstance(item, dict):
                        continue
                    usage["decisions"] += 1
                    lines.append(
                        f"- {_safe_slice(str(item.get('key') or '决策'), 60)}："
                        f"{_safe_slice(str(item.get('value') or ''), 160)}"
                    )
            memory = history.get("memory")
            if isinstance(memory, list) and memory:
                lines.append("长期记忆/偏好：")
                for item in memory[:6]:
                    if not isinstance(item, dict):
                        continue
                    usage["memory"] += 1
                    lines.append(f"- {_safe_slice(str(item.get('content') or ''), 180)}")
            executions = history.get("recent_executions")
            if isinstance(executions, list) and executions:
                lines.append("近期任务结果摘要：")
                for item in executions[:5]:
                    if not isinstance(item, dict):
                        continue
                    summary = _safe_slice(str(item.get("summary") or ""), 180)
                    if not summary:
                        continue
                    usage["recent_executions"] += 1
                    name = str(item.get("display_name") or item.get("capability_id") or "任务")
                    lines.append(f"- {_safe_slice(name, 70)}：{summary}")

    if requirements.get("include_sandbox_artifacts"):
        sandbox = workspace_data.get("sandbox_context")
        artifacts = sandbox.get("artifacts") if isinstance(sandbox, dict) else None
        if isinstance(artifacts, list) and artifacts:
            lines.append("Sandbox 产物线索：")
            for item in artifacts[:8]:
                if not isinstance(item, dict):
                    continue
                usage["sandbox_artifacts"] += 1
                kind = str(item.get("artifact_kind") or "artifact")
                path = str(item.get("path") or "")
                lines.append(f"- {kind}: {_safe_slice(path, 130)}")

    if not lines:
        return instruction, {key: value for key, value in usage.items() if value}

    context_block = "\n".join(lines)
    return (
        instruction.strip()
        + "\n\n【工作区上下文，仅用于全文改稿判断；不要编造其中没有的事实】\n"
        + context_block,
        {key: value for key, value in usage.items() if value},
    )


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
        rewrite_mode = _read_text_input(inputs, "rewrite_mode") or scope
        context_strategy = _read_text_input(inputs, "context_strategy")
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
        rewrite_instruction, used_context = _append_workspace_context_instruction(
            instruction,
            inputs=inputs,
            workspace_data=ctx.workspace_data or {},
        )
        rewrite_result = await rewrite_with_feedback(
            content=file_content,
            comment=rewrite_instruction,
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
            "reason": changes_summary or f"Prism 改稿建议：{section_title or file_path}",
            "current_hash": current_hash,
            "pending_hash": pending_hash,
            "scope": rewrite_result.get("scope") or scope,
            "rewrite_mode": rewrite_mode,
            "context_strategy": context_strategy,
            "used_context": used_context,
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
