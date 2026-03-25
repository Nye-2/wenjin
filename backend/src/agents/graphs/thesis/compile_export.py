"""Compile Export sub-graph — LLM consistency review and abstract generation."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.models.router import route_writing_model
from src.task.progress import emit_runtime_update, get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    runtime_progress_for_phase,
    upsert_runtime_block,
)
from src.workspace_features.services.thesis_feature_service import build_compile_payload

logger = logging.getLogger(__name__)


async def _emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    runtime = get_runtime_state()
    if runtime is None:
        return
    await emit_runtime_update(
        progress_value=max(runtime_progress_for_phase(runtime), 5),
        message=message,
        current_phase=current_phase,
        runtime=runtime,
        stage_transition=stage_transition,
    )


def _resolve_writing_model(requested_model: str | None) -> str:
    """Resolve a writing model with safe fallback."""
    try:
        return route_writing_model(requested_model=requested_model)
    except Exception:
        return requested_model or "default"


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
# Helper: extract chapter summaries from artifact list (pure function)
# ---------------------------------------------------------------------------
def _extract_chapter_summaries(
    artifacts: list[dict[str, Any]],
    max_content_chars: int = 500,
) -> list[dict[str, str]]:
    """Extract chapter title + truncated content from artifact dicts.

    Each artifact dict is expected to have ``type``, ``title``, and ``content``
    keys.  Only artifacts whose ``type`` equals ``"thesis_chapter"`` are
    included.  The chapter content is taken from
    ``content.get("markdown", "")`` and truncated to *max_content_chars*.

    Returns a list of ``{"title": ..., "summary": ...}`` dicts sorted by
    ``content.chapter_index`` (falling back to 999 for missing indices).
    """
    chapters: list[tuple[int, dict[str, str]]] = []
    for art in artifacts:
        if art.get("type") != "thesis_chapter":
            continue
        content = art.get("content")
        if not isinstance(content, dict):
            continue
        title = str(
            content.get("chapter_title")
            or art.get("title")
            or "未命名章节"
        )
        markdown = str(content.get("markdown") or "").strip()
        summary = markdown[:max_content_chars] if markdown else ""
        idx = content.get("chapter_index")
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = 999
        chapters.append((idx, {"title": title, "summary": summary}))

    chapters.sort(key=lambda t: t[0])
    return [ch for _, ch in chapters]


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------
async def _load_chapter_summaries(workspace_id: str) -> list[dict[str, str]]:
    """Load workspace artifacts and extract chapter summaries."""
    from src.academic.services import ArtifactService
    from src.database import get_db_session

    try:
        async with get_db_session() as db:
            service = ArtifactService(db)
            artifacts = await service.list_by_workspace(
                workspace_id=workspace_id, limit=300,
            )
        # Convert ORM objects to dicts for the pure helper
        art_dicts: list[dict[str, Any]] = []
        for art in artifacts:
            art_dicts.append({
                "type": art.type,
                "title": art.title,
                "content": art.content if isinstance(art.content, dict) else {},
            })
        return _extract_chapter_summaries(art_dicts)
    except Exception:
        logger.exception("Failed to load chapter summaries")
        return []


async def _load_literature_count(workspace_id: str) -> int:
    """Return total literature count for the workspace."""
    from src.database import get_db_session
    from src.services.literature_service import LiteratureService

    try:
        async with get_db_session() as db:
            service = LiteratureService(db)
            response = await service.list_literature(workspace_id, offset=0, limit=1)
        return int(response.get("total", 0))
    except Exception:
        logger.exception("Failed to load literature count")
        return 0


# ---------------------------------------------------------------------------
# LLM Step 1: Consistency review
# ---------------------------------------------------------------------------
_REVIEW_CONSISTENCY_PROMPT = """你是学术论文一致性审查专家。请审查以下论文各章节内容，检查整体一致性。

章节摘要:
{chapter_summaries}

参考文献数量: {literature_count}
{memory_context}

请从以下四个维度进行审查:
1. 章节逻辑连贯性 — 各章节之间是否逻辑衔接自然？
2. 引用一致性 — 参考文献使用是否前后一致？
3. 术语统一性 — 全文是否使用相同的专业术语？
4. 结构完整性 — 是否缺少必要的章节（如绪论、结论等）？

返回 JSON:
{{
  "issues": [
    {{
      "type": "logical_coherence | citation_consistency | terminology_uniformity | structural_completeness",
      "severity": "high | medium | low",
      "description": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "overall_assessment": "整体评估（2-3句话）"
}}

仅返回 JSON。"""


async def _review_consistency(
    chapter_summaries: list[dict[str, str]],
    literature_count: int,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Step 1: LLM reviews thesis consistency. Returns None on failure."""
    if not chapter_summaries:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    summaries_text = "\n".join(
        f"- 【{ch['title']}】{ch['summary']}" for ch in chapter_summaries
    )
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _REVIEW_CONSISTENCY_PROMPT.format(
        chapter_summaries=summaries_text,
        literature_count=literature_count,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("Step 1 (review_consistency) failed")
        return None


# ---------------------------------------------------------------------------
# LLM Step 2: Generate abstract and keywords
# ---------------------------------------------------------------------------
_GENERATE_ABSTRACT_PROMPT = """你是学术论文摘要撰写专家。根据以下论文信息，生成中英文摘要和关键词。

论文主题: {topic}
工作区描述: {workspace_description}

章节摘要:
{chapter_summaries}
{memory_context}

请生成:
1. 中文摘要（200-300字，学术规范）
2. 中文关键词（3-5个）
3. 英文摘要（对应中文摘要的翻译）
4. 英文关键词（对应中文关键词的翻译）

返回 JSON:
{{
  "abstract_zh": "中文摘要正文",
  "keywords_zh": ["关键词1", "关键词2", "关键词3"],
  "abstract_en": "English abstract text",
  "keywords_en": ["keyword1", "keyword2", "keyword3"]
}}

仅返回 JSON。"""


async def _generate_abstract_keywords(
    chapter_summaries: list[dict[str, str]],
    topic: str,
    workspace_description: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Step 2: LLM generates abstract and keywords. Returns None on failure."""
    if not chapter_summaries:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    summaries_text = "\n".join(
        f"- 【{ch['title']}】{ch['summary']}" for ch in chapter_summaries
    )
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _GENERATE_ABSTRACT_PROMPT.format(
        topic=topic,
        workspace_description=workspace_description,
        chapter_summaries=summaries_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("Step 2 (generate_abstract_keywords) failed")
        return None


# ---------------------------------------------------------------------------
# Helper: determine generation mode from step results
# ---------------------------------------------------------------------------
def _determine_generation_mode(
    consistency_ok: bool,
    abstract_ok: bool,
) -> str:
    """Return generation mode string based on which steps succeeded."""
    succeeded = sum([consistency_ok, abstract_ok])
    if succeeded == 2:
        return "llm"
    if succeeded == 1:
        return "partial_llm"
    return "failed"


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("compile_export", workspace_type="thesis")
async def compile_export_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute compile-export pre-processing pipeline.

    Pipeline:
        1. review_consistency — LLM checks thesis consistency across chapters
        2. generate_abstract_keywords — LLM generates abstract and keywords

    After the review/summary preprocessing, it assembles and compiles the
    thesis into a real PDF draft artifact.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = _read_payload_params(payload)
    workspace_name = str(payload.get("workspace_name") or params.get("topic") or "")
    workspace_description = str(payload.get("workspace_description", ""))
    thread_id = payload.get("thread_id")
    memory_context = initial_state.get("memory_context")
    requested_model = _read_optional_str(params.get("model_id"))
    model_id = _resolve_writing_model(requested_model)
    runtime = get_runtime_state()

    # Load data
    chapter_summaries = await _load_chapter_summaries(workspace_id)
    literature_count = await _load_literature_count(workspace_id)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "compile-inputs",
                "kind": "metrics",
                "title": "编译上下文",
                "entries": [
                    {"label": "章节数", "value": str(len(chapter_summaries))},
                    {"label": "文献数", "value": str(literature_count)},
                    {"label": "编译器", "value": str(params.get("compiler") or "xelatex")},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="编译上下文已加载",
            description=f"已整理 {len(chapter_summaries)} 个章节摘要和 {literature_count} 条文献。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在检查章节一致性...",
            current_phase="review",
            stage_transition=True,
        )

    # Step 1: Consistency review
    consistency_review = await _review_consistency(
        chapter_summaries=chapter_summaries,
        literature_count=literature_count,
        memory_context=memory_context,
        model_id=model_id,
    )
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "consistency-review",
                "kind": "text",
                "title": "一致性检查",
                "content": json.dumps(consistency_review, ensure_ascii=False, indent=2)
                if consistency_review is not None
                else "未返回一致性审查结果。",
            },
        )
        append_runtime_activity(
            runtime,
            title="一致性检查完成",
            description="已完成章节逻辑与引用一致性检查。",
            tone="success" if consistency_review is not None else "warning",
        )
        await _emit_bound_runtime(
            message="正在生成摘要和关键词并执行编译...",
            current_phase="compile",
            stage_transition=True,
        )

    # Step 2: Generate abstract and keywords
    abstract_keywords = await _generate_abstract_keywords(
        chapter_summaries=chapter_summaries,
        topic=workspace_name,
        workspace_description=workspace_description,
        memory_context=memory_context,
        model_id=model_id,
    )
    if runtime is not None and abstract_keywords is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "abstract-keywords",
                "kind": "text",
                "title": "摘要与关键词",
                "content": json.dumps(abstract_keywords, ensure_ascii=False, indent=2),
            },
        )

    # Determine pipeline results
    consistency_ok = consistency_review is not None
    abstract_ok = abstract_keywords is not None
    generation_mode = _determine_generation_mode(consistency_ok, abstract_ok)

    abstract_override: str | None = None
    keywords_override: list[str] | None = None
    if isinstance(abstract_keywords, dict):
        abstract_text = str(abstract_keywords.get("abstract_zh") or "").strip()
        if abstract_text:
            abstract_override = abstract_text
        raw_keywords = abstract_keywords.get("keywords_zh")
        if isinstance(raw_keywords, list):
            keywords_override = [
                str(item).strip()
                for item in raw_keywords
                if str(item).strip()
            ]
            keywords_override = keywords_override[:8]

    compile_payload = await build_compile_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        thread_id=str(thread_id) if thread_id else None,
        template=str(params.get("template") or "default"),
        compiler=str(params.get("compiler") or "xelatex"),
        bibliography_style=str(params.get("bibliography_style") or "gbt7714"),
        abstract_override=abstract_override,
        keywords_override=keywords_override,
    )
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "compile-result",
                "kind": "metrics",
                "title": "编译结果",
                "entries": [
                    {"label": "编译状态", "value": str(compile_payload.get("compile_status") or "unknown")},
                    {"label": "页数", "value": str(compile_payload.get("page_count") or 0)},
                    {"label": "模板", "value": str(compile_payload.get("template") or "default")},
                ],
            },
        )
        compile_logs = str(compile_payload.get("compile_logs") or "")
        if compile_logs:
            upsert_runtime_block(
                runtime,
                {
                    "id": "compile-logs",
                    "kind": "text",
                    "title": "编译日志",
                    "content": compile_logs[:1800],
                },
            )
        append_runtime_activity(
            runtime,
            title="编译流程完成",
            description="已生成摘要、关键词并完成编译尝试。",
            tone="success" if compile_payload.get("compile_status") == "success" else "warning",
        )
        await _emit_bound_runtime(
            message="正在整理编译导出产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    return {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "consistency_review": consistency_review,
        "abstract_keywords": abstract_keywords,
        "compile_status": compile_payload.get("compile_status"),
        "pdf_path": compile_payload.get("pdf_path"),
        "pdf_url": compile_payload.get("pdf_url"),
        "page_count": compile_payload.get("page_count"),
        "compile_error": compile_payload.get("compile_error"),
        "compile_logs": compile_payload.get("compile_logs"),
        "latex_content": compile_payload.get("latex_content"),
        "bib_content": compile_payload.get("bib_content"),
        "keywords": compile_payload.get("keywords"),
        "abstract_source": compile_payload.get("abstract_source"),
        "source_summary": compile_payload.get("source_summary"),
        "template": compile_payload.get("template"),
        "compiler": compile_payload.get("compiler"),
        "bibliography_style": compile_payload.get("bibliography_style"),
        "paper_title": compile_payload.get("paper_title"),
        "model_id": model_id,
        "chapter_count": len(chapter_summaries),
        "literature_count": literature_count,
        "generation_mode": generation_mode,
        "pipeline_steps": {
            "consistency_review": consistency_ok,
            "abstract_generation": abstract_ok,
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
