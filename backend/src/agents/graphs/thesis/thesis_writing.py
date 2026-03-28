"""Thesis Writing Enhancement sub-graph — self-review and revision loop."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.models.router import route_writing_model, validate_requested_model
from src.task.progress import get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    emit_bound_runtime as _emit_bound_runtime,
    runtime_progress_for_phase,
    upsert_runtime_block,
)
from src.workspace_features.services.thesis_writing_service import (
    build_chapter_payload,
    build_outline_payload,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Max revision rounds
# ---------------------------------------------------------------------------
_MAX_REVISION_ROUNDS = 2


def _resolve_writing_model(requested_model: str | None) -> str:
    """Resolve a writing model without silently rerouting invalid selections."""
    requested = validate_requested_model(
        requested_model,
        allowed_categories=("gen", "tool"),
        require_tools=False,
    )
    return route_writing_model(requested_model=requested)


def _coerce_int(value: Any, default: int) -> int:
    """Best-effort int conversion with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(value: Any) -> list[str]:
    """Normalize a mixed list-like value into non-empty strings."""
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw in value:
        text = str(raw or "").strip()
        if text:
            items.append(text)
    return items


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("thesis_writing", workspace_type="thesis")
async def thesis_writing_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute thesis writing enhancement pipeline.

    Supports multiple modes based on ``payload.params.action``:

    * ``"generate_outline"`` — Build thesis outline payload.
    * ``"write_chapter"`` — Build chapter draft payload.
    * ``"write_all"`` — Build outline and all chapter drafts in one run.
    * ``"review_section"`` — Review an existing section and provide feedback.
    * ``"revise_section"`` — Revise a section based on feedback.
    * *default* — Full review-and-revise loop (max 2 rounds).
    """
    params = _read_payload_params(payload)
    workspace_id = str(payload.get("workspace_id") or "").strip() or None
    action = str(params.get("action", "")).strip()
    memory_context = initial_state.get("memory_context")
    requested_model = _read_optional_str(params.get("model_id"))
    model_id = _resolve_writing_model(requested_model)

    if action == "generate_outline":
        return await _handle_generate_outline(
            params,
            workspace_id=workspace_id,
            model_id=model_id,
        )

    if action == "write_chapter":
        return await _handle_write_chapter(params, model_id=model_id)

    if action == "write_all":
        return await _handle_write_all(
            params,
            workspace_id=workspace_id,
            model_id=model_id,
        )

    if action == "review_section":
        return await _handle_review_section(params, memory_context, model_id=model_id)

    if action == "revise_section":
        return await _handle_revise_section(params, memory_context, model_id=model_id)

    # Default: full review + auto-revise loop
    return await _handle_review_and_revise(params, memory_context, model_id=model_id)


# ---------------------------------------------------------------------------
# Mode 1: generate_outline
# ---------------------------------------------------------------------------
async def _handle_generate_outline(
    params: dict[str, Any],
    *,
    workspace_id: str | None = None,
    model_id: str = "default",
) -> dict[str, Any]:
    """Build an outline payload for thesis writing Step 1."""
    paper_title = str(
        params.get("paper_title")
        or params.get("topic")
        or "未命名论文"
    ).strip() or "未命名论文"
    target_words = max(1000, _coerce_int(params.get("target_words"), 20000))
    literature_count = max(0, _coerce_int(params.get("literature_count"), 0))
    deep_research_artifact_ids = _coerce_str_list(
        params.get("deep_research_artifact_ids")
    )
    runtime = get_runtime_state()
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "outline-inputs",
                "kind": "metrics",
                "title": "大纲输入",
                "entries": [
                    {"label": "论文标题", "value": paper_title},
                    {"label": "目标字数", "value": str(target_words)},
                    {"label": "文献数", "value": str(literature_count)},
                    {"label": "深度调研产物", "value": str(len(deep_research_artifact_ids))},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="大纲参数已整理",
            description="已确认论文标题、目标字数和上下文产物。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成论文大纲...",
            current_phase="outline",
            stage_transition=True,
        )

    outline_payload = await build_outline_payload(
        paper_title=paper_title,
        target_words=target_words,
        literature_count=literature_count,
        deep_research_artifact_ids=deep_research_artifact_ids,
        workspace_id=workspace_id,
        preferred_model=model_id,
    )
    if runtime is not None:
        outline = outline_payload.get("outline") if isinstance(outline_payload.get("outline"), dict) else {}
        chapters = outline.get("chapters") if isinstance(outline, dict) else []
        if isinstance(chapters, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "outline-chapters",
                    "kind": "list",
                    "title": "章节大纲",
                    "items": [
                        {
                            "title": str(chapter.get("title") or "未命名章节"),
                            "description": "、".join(str(item) for item in (chapter.get("keyPoints") or [])[:3]),
                            "meta": str(chapter.get("position") or ""),
                            "badge": str(chapter.get("targetWords") or ""),
                        }
                        for chapter in chapters[:8]
                        if isinstance(chapter, dict)
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="论文大纲已生成",
            description=f"已输出 {len(chapters) if isinstance(chapters, list) else 0} 个章节。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理论文大纲产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    return {
        "action": "generate_outline",
        "paper_title": outline_payload.get("paper_title", paper_title),
        "outline": outline_payload.get("outline", {}),
        "source_context": outline_payload.get("source_context", {}),
        "schema_version": outline_payload.get("schema_version", "v1"),
        "model_id": model_id,
        "generation_mode": outline_payload.get("generation_mode", "llm"),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mode 2: write_chapter
# ---------------------------------------------------------------------------
async def _handle_write_chapter(
    params: dict[str, Any],
    *,
    model_id: str = "default",
) -> dict[str, Any]:
    """Build a chapter payload for thesis writing Step 2."""
    chapter_index = max(0, _coerce_int(params.get("chapter_index"), 0))
    chapter_title = str(
        params.get("chapter_title")
        or f"第{chapter_index + 1}章"
    ).strip() or f"第{chapter_index + 1}章"
    paper_title = str(
        params.get("paper_title")
        or "未命名论文"
    ).strip() or "未命名论文"
    target_words = max(800, _coerce_int(params.get("target_words"), 2500))
    references_used = _coerce_str_list(params.get("references_used"))
    runtime = get_runtime_state()
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "chapter-inputs",
                "kind": "metrics",
                "title": "章节输入",
                "entries": [
                    {"label": "论文标题", "value": paper_title},
                    {"label": "章节标题", "value": chapter_title},
                    {"label": "章节序号", "value": str(chapter_index)},
                    {"label": "目标字数", "value": str(target_words)},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="章节参数已整理",
            description="已确认章节标题、字数和引用上下文。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成章节草稿...",
            current_phase="draft",
            stage_transition=True,
        )

    chapter_payload = await build_chapter_payload(
        paper_title=paper_title,
        chapter_index=chapter_index,
        chapter_title=chapter_title,
        target_words=target_words,
        references_used=references_used,
        preferred_model=model_id,
    )
    if runtime is not None:
        content_text = str(chapter_payload.get("markdown") or chapter_payload.get("content") or "")
        upsert_runtime_block(
            runtime,
            {
                "id": "chapter-draft",
                "kind": "text",
                "title": chapter_title,
                "content": content_text[:1800],
            },
        )
        references = chapter_payload.get("references_used") or references_used
        if isinstance(references, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "chapter-references",
                    "kind": "list",
                    "title": "参考文献",
                    "items": [
                        {"title": str(reference), "description": ""}
                        for reference in references[:8]
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="章节草稿已生成",
            description=f"已完成 {chapter_title} 草稿生成。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理章节草稿产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    return {
        "action": "write_chapter",
        "paper_title": paper_title,
        "chapter": chapter_payload,
        "schema_version": chapter_payload.get("schema_version", "v1"),
        "model_id": model_id,
        "generation_mode": chapter_payload.get("generation_mode", "llm"),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mode 2b: write_all
# ---------------------------------------------------------------------------
async def _handle_write_all(
    params: dict[str, Any],
    *,
    workspace_id: str | None = None,
    model_id: str = "default",
) -> dict[str, Any]:
    """Build outline and chapter payloads for full-text generation."""
    paper_title = str(
        params.get("paper_title")
        or params.get("topic")
        or "未命名论文"
    ).strip() or "未命名论文"
    target_words = max(1000, _coerce_int(params.get("target_words"), 20000))
    literature_count = max(0, _coerce_int(params.get("literature_count"), 0))
    deep_research_artifact_ids = _coerce_str_list(
        params.get("deep_research_artifact_ids")
    )
    references_used = _coerce_str_list(params.get("references_used"))

    runtime = get_runtime_state()
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "write-all-inputs",
                "kind": "metrics",
                "title": "全文生成输入",
                "entries": [
                    {"label": "论文标题", "value": paper_title},
                    {"label": "目标字数", "value": str(target_words)},
                    {"label": "文献数", "value": str(literature_count)},
                    {"label": "深度调研产物", "value": str(len(deep_research_artifact_ids))},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="全文生成参数已整理",
            description="准备生成大纲并批量写作章节。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成论文大纲...",
            current_phase="outline",
            stage_transition=True,
        )

    outline_payload = await build_outline_payload(
        paper_title=paper_title,
        target_words=target_words,
        literature_count=literature_count,
        deep_research_artifact_ids=deep_research_artifact_ids,
        workspace_id=workspace_id,
        preferred_model=model_id,
    )
    outline = (
        outline_payload.get("outline")
        if isinstance(outline_payload.get("outline"), dict)
        else {}
    )
    chapters = outline.get("chapters") if isinstance(outline.get("chapters"), list) else []

    chapter_payloads: list[dict[str, Any]] = []
    if chapters:
        if runtime is not None:
            await _emit_bound_runtime(
                message="正在批量生成章节草稿...",
                current_phase="draft",
                stage_transition=True,
            )

        for index, chapter in enumerate(chapters):
            if not isinstance(chapter, dict):
                continue
            chapter_title = str(chapter.get("title") or f"第{index + 1}章")
            chapter_target_words = max(
                800,
                _coerce_int(chapter.get("targetWords"), max(1000, target_words // max(len(chapters), 1))),
            )
            chapter_payload = await build_chapter_payload(
                paper_title=paper_title,
                chapter_index=index,
                chapter_title=chapter_title,
                target_words=chapter_target_words,
                references_used=references_used,
                preferred_model=model_id,
            )
            chapter_payloads.append(chapter_payload)

    if runtime is not None:
        if chapters:
            upsert_runtime_block(
                runtime,
                {
                    "id": "write-all-outline-chapters",
                    "kind": "list",
                    "title": "大纲章节",
                    "items": [
                        {
                            "title": str(chapter.get("title") or "未命名章节"),
                            "description": "、".join(str(item) for item in (chapter.get("keyPoints") or [])[:3]),
                            "meta": str(chapter.get("position") or ""),
                            "badge": str(chapter.get("targetWords") or ""),
                        }
                        for chapter in chapters[:10]
                        if isinstance(chapter, dict)
                    ],
                },
            )
        if chapter_payloads:
            upsert_runtime_block(
                runtime,
                {
                    "id": "write-all-generated-chapters",
                    "kind": "list",
                    "title": "章节草稿",
                    "items": [
                        {
                            "title": str(chapter.get("chapter_title") or "未命名章节"),
                            "description": str(chapter.get("markdown") or "")[:220],
                            "meta": f"目标 {chapter.get('target_words') or 0} 字",
                            "badge": str(chapter.get("estimated_words") or ""),
                        }
                        for chapter in chapter_payloads[:10]
                        if isinstance(chapter, dict)
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="全文草稿已生成",
            description=f"已生成大纲和 {len(chapter_payloads)} 个章节草稿。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理全文生成产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    return {
        "action": "write_all",
        "paper_title": outline_payload.get("paper_title", paper_title),
        "outline": outline,
        "chapters": chapter_payloads,
        "source_context": outline_payload.get("source_context", {}),
        "schema_version": outline_payload.get("schema_version", "v1"),
        "model_id": model_id,
        "generation_mode": "llm",
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mode 3: review_section
# ---------------------------------------------------------------------------
async def _handle_review_section(
    params: dict[str, Any],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any]:
    """Review an existing section and return structured feedback."""
    section_title = str(params.get("section_title", ""))
    section_content = str(params.get("section_content", ""))
    section_plan = params.get("section_plan")

    review = await _review_section(
        section_title=section_title,
        section_content=section_content,
        section_plan=section_plan,
        memory_context=memory_context,
        model_id=model_id,
    )

    if review is None:
        raise RuntimeError("review_section_llm_failed: model did not return valid JSON review")

    return {
        "action": "review_section",
        "section_title": section_title,
        "review": review,
        "model_id": model_id,
        "generation_mode": "llm",
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mode 4: revise_section
# ---------------------------------------------------------------------------
async def _handle_revise_section(
    params: dict[str, Any],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any]:
    """Revise a section based on review feedback."""
    section_title = str(params.get("section_title", ""))
    section_content = str(params.get("section_content", ""))
    revision_instructions = str(params.get("revision_instructions", ""))
    try:
        revision_round = int(params.get("revision_round", 1))
    except (TypeError, ValueError):
        revision_round = 1

    # Clamp revision round
    revision_round = max(1, min(revision_round, _MAX_REVISION_ROUNDS))

    revision = await _revise_section(
        section_title=section_title,
        section_content=section_content,
        revision_instructions=revision_instructions,
        memory_context=memory_context,
        model_id=model_id,
    )

    if revision is None:
        raise RuntimeError("revise_section_llm_failed: model did not return valid JSON revision")

    revised_content = revision.get("revised_content", section_content)
    changes_summary = revision.get("changes_summary", "")

    return {
        "action": "revise_section",
        "section_title": section_title,
        "revised_content": revised_content,
        "revision_round": revision_round,
        "changes_summary": changes_summary,
        "model_id": model_id,
        "generation_mode": "llm",
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Default mode: review + auto-revise loop
# ---------------------------------------------------------------------------
async def _handle_review_and_revise(
    params: dict[str, Any],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any]:
    """Full review-and-revise loop (max 2 rounds)."""
    section_title = str(params.get("section_title", ""))
    section_content = str(params.get("section_content", ""))
    section_plan = params.get("section_plan")

    original_content = section_content
    current_content = section_content
    rounds: list[dict[str, Any]] = []

    for round_num in range(1, _MAX_REVISION_ROUNDS + 1):
        # Review current content
        review = await _review_section(
            section_title=section_title,
            section_content=current_content,
            section_plan=section_plan,
            memory_context=memory_context,
            model_id=model_id,
        )

        if review is None:
            raise RuntimeError(
                f"review_and_revise_failed: review round {round_num} returned invalid output"
            )

        round_result: dict[str, Any] = {
            "round": round_num,
            "review": review,
            "revised_content": None,
        }

        if not review.get("revision_needed", False):
            rounds.append(round_result)
            break

        # Revise based on instructions
        revision_instructions = review.get("revision_instructions") or ""
        revision = await _revise_section(
            section_title=section_title,
            section_content=current_content,
            revision_instructions=revision_instructions,
            memory_context=memory_context,
            model_id=model_id,
        )

        if revision is None:
            raise RuntimeError(
                f"review_and_revise_failed: revise round {round_num} returned invalid output"
            )

        revised_content = revision.get("revised_content", current_content)
        round_result["revised_content"] = revised_content
        current_content = revised_content

        rounds.append(round_result)

    return {
        "action": "review_and_revise",
        "section_title": section_title,
        "original_content": original_content,
        "final_content": current_content,
        "rounds": rounds,
        "total_rounds": len(rounds),
        "model_id": model_id,
        "generation_mode": "llm",
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------
_REVIEW_PROMPT = """你是严谨的学术论文审稿人。请审阅以下论文章节，返回 JSON。

章节标题: {title}
章节内容:
{content}

{plan_context}
{memory_context}

评审维度:
1. 逻辑连贯性（论证是否清晰流畅）
2. 引用规范性（是否恰当引用文献）
3. 学术写作质量（用词、句式、格式）
4. 内容深度与学术严谨性
5. 是否符合章节规划要求

返回格式:
{{
  "overall_score": 7.5,
  "issues": [
    {{"type": "logic|citation|writing|depth|plan", "severity": "high|medium|low", "description": "问题描述", "suggestion": "修改建议"}}
  ],
  "strengths": ["优点1", "优点2"],
  "revision_needed": true,
  "revision_instructions": "具体的修改指导（如果需要修改）"
}}

仅返回 JSON。"""

_REVISE_PROMPT = """你是学术论文修改专家。请根据审稿意见修改以下章节。

章节标题: {title}
当前内容:
{content}

修改指导:
{instructions}

{memory_context}

要求:
1. 保持章节结构和格式
2. 针对性修改，不要大幅重写无问题的部分
3. 保持学术写作风格
4. 确保引用格式一致

返回格式:
{{
  "revised_content": "修改后的完整章节内容",
  "changes_summary": "简述做了哪些修改"
}}

仅返回 JSON。"""


# ---------------------------------------------------------------------------
# Helper: LLM review
# ---------------------------------------------------------------------------
async def _review_section(
    section_title: str,
    section_content: str,
    section_plan: dict[str, Any] | None,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """LLM-powered section review. Returns validated dict or None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    plan_text = ""
    if section_plan:
        purpose = section_plan.get("purpose", "")
        key_points = section_plan.get("key_points", [])
        if purpose or key_points:
            plan_text = f"章节规划:\n目的: {purpose}\n关键要点: {', '.join(key_points)}"

    mem_text = f"用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _REVIEW_PROMPT.format(
        title=section_title,
        content=section_content,
        plan_context=plan_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_response(content)
        if parsed is not None and _validate_review_result(parsed):
            return parsed
        return None
    except Exception:
        logger.exception("Section review LLM call failed")
        return None


# ---------------------------------------------------------------------------
# Helper: LLM revision
# ---------------------------------------------------------------------------
async def _revise_section(
    section_title: str,
    section_content: str,
    revision_instructions: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """LLM-powered section revision. Returns dict or None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    mem_text = f"用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _REVISE_PROMPT.format(
        title=section_title,
        content=section_content,
        instructions=revision_instructions,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_response(content)
        if parsed is not None and "revised_content" in parsed:
            return parsed
        return None
    except Exception:
        logger.exception("Section revision LLM call failed")
        return None


# ---------------------------------------------------------------------------
# Helper: parse JSON from LLM response
# ---------------------------------------------------------------------------
def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Helper: validate review result structure
# ---------------------------------------------------------------------------
def _validate_review_result(review: dict[str, Any]) -> bool:
    """Validate that a review dict has the required structure and types."""
    required_keys = {"overall_score", "issues", "strengths", "revision_needed"}
    if not required_keys.issubset(review.keys()):
        return False

    if not isinstance(review["overall_score"], (int, float)):
        return False
    if not isinstance(review["issues"], list):
        return False
    if not isinstance(review["strengths"], list):
        return False
    if not isinstance(review["revision_needed"], bool):
        return False

    return True
