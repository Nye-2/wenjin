"""Compile Export sub-graph — LLM consistency review and abstract generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.thesis_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)


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
) -> dict[str, Any] | None:
    """Step 1: LLM reviews thesis consistency. Returns None on failure."""
    if not chapter_summaries:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.3)
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
) -> dict[str, Any] | None:
    """Step 2: LLM generates abstract and keywords. Returns None on failure."""
    if not chapter_summaries:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.3)
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
    return "template_fallback"


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("compile_export")
async def compile_export_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute compile-export pre-processing pipeline.

    Pipeline:
        1. review_consistency — LLM checks thesis consistency across chapters
        2. generate_abstract_keywords — LLM generates abstract and keywords

    This sub-graph does NOT perform the actual LaTeX compilation.  It produces
    a consistency review and auto-generated abstract/keywords that the
    existing compile handler can consume.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(
        payload.get("workspace_name", payload.get("params", {}).get("topic", ""))
    )
    workspace_description = str(payload.get("workspace_description", ""))
    memory_context = initial_state.get("knowledge_context")

    # Load data
    chapter_summaries = await _load_chapter_summaries(workspace_id)
    literature_count = await _load_literature_count(workspace_id)

    # Step 1: Consistency review
    consistency_review = await _review_consistency(
        chapter_summaries=chapter_summaries,
        literature_count=literature_count,
        memory_context=memory_context,
    )

    # Step 2: Generate abstract and keywords
    abstract_keywords = await _generate_abstract_keywords(
        chapter_summaries=chapter_summaries,
        topic=workspace_name,
        workspace_description=workspace_description,
        memory_context=memory_context,
    )

    # Determine pipeline results
    consistency_ok = consistency_review is not None
    abstract_ok = abstract_keywords is not None
    generation_mode = _determine_generation_mode(consistency_ok, abstract_ok)

    return {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "consistency_review": consistency_review,
        "abstract_keywords": abstract_keywords,
        "chapter_count": len(chapter_summaries),
        "literature_count": literature_count,
        "generation_mode": generation_mode,
        "pipeline_steps": {
            "consistency_review": consistency_ok,
            "abstract_generation": abstract_ok,
        },
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
