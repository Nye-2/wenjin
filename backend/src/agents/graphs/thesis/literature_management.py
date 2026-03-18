"""Literature Management sub-graph — LLM-powered analysis replacing template stats."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)


@register_feature_graph("literature_management", workspace_type="thesis")
async def literature_management_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute literature management with LLM-enhanced analysis.

    Pipeline: load literature -> compute stats -> LLM topic clustering -> LLM recommendations
    Falls back to template mode if LLM unavailable.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    focus_topic = str(payload.get("params", {}).get("topic", payload.get("workspace_name", "")))

    # Step 1: Load literature
    literature = await _load_literature(workspace_id)

    # Step 2: Compute base statistics (always works, no LLM needed)
    stats = _compute_statistics(literature, focus_topic)

    # Step 3: LLM-powered analysis (with fallback)
    llm_analysis = await _llm_analyze_literature(literature, focus_topic, initial_state.get("knowledge_context"))

    # Merge LLM analysis into stats
    if llm_analysis:
        stats["topic_clusters"] = llm_analysis.get("topic_clusters", [])
        stats["quality_assessment"] = llm_analysis.get("quality_assessment", "")
        stats["smart_recommendations"] = llm_analysis.get("recommendations", [])
        stats["generation_mode"] = "llm"
    else:
        stats["generation_mode"] = "template_fallback"

    stats["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    return stats


async def _load_literature(workspace_id: str) -> list[dict[str, Any]]:
    """Load workspace literature from DB."""
    from src.database import get_db_session
    from src.services.literature_service import LiteratureService

    try:
        async with get_db_session() as db:
            service = LiteratureService(db)
            response = await service.list_literature(workspace_id, offset=0, limit=120)
        items = response.get("items")
        return items if isinstance(items, list) else []
    except Exception:
        logger.exception("Failed to load literature")
        return []


def _compute_statistics(literature: list[dict], focus_topic: str) -> dict[str, Any]:
    """Compute base statistics (no LLM needed)."""
    total = len(literature)
    if total == 0:
        return {
            "summary": {"total": 0, "core_count": 0, "focus_topic": focus_topic},
            "top_cited": [],
            "by_source": {},
            "by_year": {},
            "quality_check": {"missing_abstract": 0, "missing_doi": 0},
            "recommended_actions": ["添加更多参考文献到工作区"],
        }

    core_count = sum(1 for p in literature if (p.get("citations") or 0) >= 10)
    by_source = dict(Counter(str(p.get("source") or "unknown") for p in literature))
    by_year = dict(Counter(str(p.get("year") or "unknown") for p in literature))
    missing_abstract = sum(1 for p in literature if not p.get("abstract"))
    missing_doi = sum(1 for p in literature if not p.get("doi"))

    sorted_by_citations = sorted(literature, key=lambda p: p.get("citations") or 0, reverse=True)
    top_cited = [
        {"title": p.get("title", ""), "citations": p.get("citations", 0), "year": p.get("year")}
        for p in sorted_by_citations[:10]
    ]

    return {
        "summary": {
            "total": total,
            "core_count": core_count,
            "focus_topic": focus_topic,
            "avg_citations": round(sum(p.get("citations", 0) for p in literature) / total, 1),
        },
        "top_cited": top_cited,
        "by_source": by_source,
        "by_year": by_year,
        "quality_check": {"missing_abstract": missing_abstract, "missing_doi": missing_doi},
        "recommended_actions": _build_recommendations(total, missing_abstract, missing_doi, core_count),
    }


def _build_recommendations(total: int, missing_abstract: int, missing_doi: int, core_count: int) -> list[str]:
    """Rule-based recommendations."""
    actions: list[str] = []
    if total < 15:
        actions.append(f"当前仅 {total} 篇文献，建议补充至 15 篇以上")
    if missing_abstract > total * 0.3:
        actions.append(f"{missing_abstract} 篇缺少摘要，建议补充")
    if missing_doi > total * 0.3:
        actions.append(f"{missing_doi} 篇缺少 DOI，影响引用规范性")
    if core_count < 3:
        actions.append("核心文献不足 3 篇，建议添加高引用量文献")
    return actions or ["文献库质量良好"]


LLM_ANALYSIS_PROMPT = """你是学术文献分析专家。分析以下文献列表，返回 JSON:

文献列表:
{literature_summary}

用户研究方向: {focus_topic}
{memory_context}

返回格式:
{{
  "topic_clusters": [
    {{"name": "主题名", "papers_count": 3, "description": "简述"}}
  ],
  "quality_assessment": "对文献库整体质量的评估（2-3句话）",
  "recommendations": ["具体改进建议1", "具体改进建议2"]
}}

仅返回 JSON。"""


async def _llm_analyze_literature(
    literature: list[dict],
    focus_topic: str,
    memory_context: str | None,
) -> dict[str, Any] | None:
    """LLM-powered literature analysis. Returns None on failure."""
    if not literature:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.3)
    except Exception:
        return None

    # Prepare literature summary (limit to avoid token overflow)
    summaries = []
    for p in literature[:50]:
        title = p.get("title", "Unknown")
        year = p.get("year", "")
        citations = p.get("citations", 0)
        abstract = (p.get("abstract") or "")[:200]
        summaries.append(f"- {title} ({year}, cited {citations}x): {abstract}")
    lit_text = "\n".join(summaries)

    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = LLM_ANALYSIS_PROMPT.format(
        literature_summary=lit_text,
        focus_topic=focus_topic,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("LLM literature analysis failed")
        return None


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
