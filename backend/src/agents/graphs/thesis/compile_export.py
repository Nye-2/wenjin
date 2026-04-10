"""Compile Export sub-graph — LLM consistency review and abstract generation."""

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
    upsert_runtime_block,
)
from src.task.runtime_blocks import (
    emit_bound_runtime as _emit_bound_runtime,
)
from src.workspace_features.latex_sync import compile_thesis_payload
from src.workspace_features.services.llm_json import (
    build_json_prompt,
    invoke_json_chat_model,
    parse_json_payload,
)
from src.workspace_features.services.thesis_feature_service import (
    build_compile_payload,
    extract_thesis_chapter_summaries,
)
from src.workspace_features.services.thesis_feature_service import (
    load_thesis_chapter_summaries as _load_chapter_summaries,
)
from src.workspace_features.services.thesis_feature_service import (
    load_thesis_literature_count as _load_literature_count,
)
from src.workspace_features.services.thesis_feature_service import (
    load_thesis_outline_context as _load_outline_context,
)

logger = logging.getLogger(__name__)


def _resolve_writing_model(requested_model: str | None) -> str:
    """Resolve a writing model without silently rerouting invalid selections."""
    requested = validate_requested_model(
        requested_model,
        allowed_categories=("gen", "tool"),
        require_tools=False,
    )
    return route_writing_model(requested_model=requested)


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Compatibility wrapper for tests around JSON parsing behavior."""
    return parse_json_payload(text)


def _extract_chapter_summaries(
    artifacts: list[dict[str, Any]],
    max_content_chars: int = 500,
) -> list[dict[str, str]]:
    """Compatibility wrapper for chapter-summary extraction tests."""
    return extract_thesis_chapter_summaries(
        artifacts,
        max_content_chars=max_content_chars,
    )


_REVIEW_CONSISTENCY_SCHEMA = """{
  "issues": [
    {
      "type": "logical_coherence | citation_consistency | terminology_uniformity | structural_completeness",
      "severity": "high | medium | low",
      "description": "问题描述",
      "suggestion": "修改建议"
    }
  ],
  "overall_assessment": "整体评估（2-3句话）"
}"""


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

    summaries_text = "\n".join(
        f"- 【{ch['title']}】{ch['summary']}" for ch in chapter_summaries
    )
    prompt = build_json_prompt(
        instruction="请审查论文章节摘要的一致性，识别会影响成稿质量的关键问题。",
        context_sections=(
            ("章节摘要", summaries_text),
            ("补充指标", [f"参考文献数量：{literature_count}"]),
            ("工作记忆", memory_context),
        ),
        schema=_REVIEW_CONSISTENCY_SCHEMA,
        requirements=(
            "优先指出真正会影响逻辑、引用、术语统一和结构完整性的高价值问题。",
            "issues 按严重程度从高到低排序；没有问题时返回空数组。",
            "overall_assessment 需要明确说明当前稿件是否适合进入编译导出阶段。",
        ),
        output_language="中文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是学术论文一致性审查专家。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.2,
    )
    if isinstance(parsed, dict):
        return parsed
    if generation_error:
        logger.warning("Step 1 (review_consistency) failed: %s", generation_error)
        return None
    return None


_GENERATE_ABSTRACT_SCHEMA = """{
  "abstract_zh": "中文摘要正文",
  "keywords_zh": ["关键词1", "关键词2", "关键词3"],
  "abstract_en": "English abstract text",
  "keywords_en": ["keyword1", "keyword2", "keyword3"]
}"""


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

    summaries_text = "\n".join(
        f"- 【{ch['title']}】{ch['summary']}" for ch in chapter_summaries
    )
    prompt = build_json_prompt(
        instruction="请基于论文主题与章节摘要，生成可直接用于学位论文导出的中英文摘要和关键词。",
        context_sections=(
            ("论文主题", topic),
            ("工作区描述", workspace_description),
            ("章节摘要", summaries_text),
            ("工作记忆", memory_context),
        ),
        schema=_GENERATE_ABSTRACT_SCHEMA,
        requirements=(
            "中文摘要控制在 200-300 字，突出研究背景、方法、结果和价值。",
            "英文摘要应忠实对应中文摘要，避免逐字硬译和不自然表达。",
            "关键词保持 3-5 个，术语准确、便于检索。",
            "如果章节信息不足，要在摘要中保守表达，不要编造实验结果。",
        ),
        output_language="中文；abstract_en 和 keywords_en 使用英文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是学术论文摘要撰写专家。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.2,
    )
    if isinstance(parsed, dict):
        return parsed
    if generation_error:
        logger.warning("Step 2 (generate_abstract_keywords) failed: %s", generation_error)
        return None
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
    outline_context = await _load_outline_context(workspace_id)
    chapter_summaries = await _load_chapter_summaries(workspace_id)
    literature_count = await _load_literature_count(workspace_id)
    paper_title = str(
        outline_context.get("paper_title")
        or workspace_name
        or params.get("topic")
        or "未命名论文"
    ).strip() or "未命名论文"
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
        topic=paper_title,
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
    compile_result = await compile_thesis_payload(
        workspace_id=workspace_id,
        payload=compile_payload,
    )
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "compile-result",
                "kind": "metrics",
                "title": "编译结果",
                "entries": [
                    {"label": "编译状态", "value": str(compile_result.compile_status or "unknown")},
                    {"label": "页数", "value": str(compile_result.page_count or 0)},
                    {"label": "模板", "value": str(compile_payload.get("template") or "default")},
                ],
            },
        )
        compile_logs = str(compile_result.compile_logs or "")
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
            tone="success" if compile_result.compile_status == "success" else "warning",
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
        "latex_project_id": compile_result.latex_project_id,
        "main_file": compile_result.main_file,
        "compile_status": compile_result.compile_status,
        "pdf_path": compile_result.pdf_path,
        "pdf_url": compile_result.pdf_url,
        "pdf_endpoint": compile_result.pdf_endpoint,
        "page_count": compile_result.page_count,
        "compile_error": compile_result.compile_error,
        "compile_logs": compile_result.compile_logs,
        "latex_content": compile_payload.get("latex_content"),
        "bib_content": compile_payload.get("bib_content"),
        "keywords": compile_payload.get("keywords"),
        "abstract_source": compile_payload.get("abstract_source"),
        "source_summary": compile_payload.get("source_summary"),
        "sync_conflicts": compile_result.sync_conflicts,
        "template": compile_payload.get("template"),
        "compiler": compile_payload.get("compiler"),
        "bibliography_style": compile_payload.get("bibliography_style"),
        "paper_title": compile_payload.get("paper_title") or paper_title,
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
