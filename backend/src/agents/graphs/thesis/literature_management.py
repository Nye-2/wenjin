"""Literature Management sub-graph — LLM-powered literature management analysis."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.models.router import route_model, validate_requested_model
from src.task.progress import emit_runtime_update, get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    runtime_progress_for_phase,
    upsert_runtime_block,
)

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


def _resolve_management_model(requested_model: str | None) -> str:
    """Resolve a model for literature management analysis without silent rerouting."""
    requested = validate_requested_model(
        requested_model,
        allowed_categories=("tool", "gen"),
        require_tools=False,
    )
    return route_model(
        requested_model=requested,
        preferred_categories=("tool", "gen"),
        allowed_categories=("tool", "gen"),
        require_tools=False,
    )


@register_feature_graph("literature_management", workspace_type="thesis")
async def literature_management_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute literature management with LLM-enhanced analysis.

    Pipeline: load literature -> compute stats -> LLM topic clustering -> LLM recommendations.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = _read_payload_params(payload)
    focus_topic = str(params.get("topic") or payload.get("workspace_name") or "")
    requested_model = _read_optional_str(params.get("model_id"))
    model_id = _resolve_management_model(requested_model)
    runtime = get_runtime_state()

    # Step 1: Load literature
    literature = await _load_literature(workspace_id)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "literature-context",
                "kind": "metrics",
                "title": "文献上下文",
                "entries": [
                    {"label": "主题", "value": focus_topic or "研究主题"},
                    {"label": "文献总数", "value": str(len(literature))},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="文献已加载",
            description=f"已读取 {len(literature)} 条工作区文献，开始统计盘点。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在统计文献质量与结构...",
            current_phase="analyze",
            stage_transition=True,
        )

    # Step 2: Compute base statistics (always works, no LLM needed)
    stats = _compute_statistics(literature, focus_topic)

    # Step 3: LLM-powered analysis
    llm_analysis = await _llm_analyze_literature(
        literature,
        focus_topic,
        initial_state.get("memory_context"),
        model_id=model_id,
    )

    # Merge LLM analysis into stats
    if llm_analysis:
        stats["topic_clusters"] = llm_analysis.get("topic_clusters", [])
        stats["quality_assessment"] = llm_analysis.get("quality_assessment", "")
        stats["smart_recommendations"] = llm_analysis.get("recommendations", [])
        stats["generation_mode"] = "llm"
    else:
        stats["generation_mode"] = "rule_based"

    stats["model_id"] = model_id
    stats["generated_at"] = datetime.now(tz=UTC).isoformat()
    if runtime is not None:
        summary = stats.get("summary") if isinstance(stats.get("summary"), dict) else {}
        upsert_runtime_block(
            runtime,
            {
                "id": "literature-summary",
                "kind": "metrics",
                "title": "文献盘点",
                "entries": [
                    {"label": "总文献", "value": str(summary.get("total") or 0)},
                    {"label": "核心文献", "value": str(summary.get("core_count") or 0)},
                    {"label": "平均引用", "value": str(summary.get("avg_citations") or 0)},
                ],
            },
        )
        if isinstance(stats.get("top_cited"), list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "top-cited",
                    "kind": "list",
                    "title": "高引用文献",
                    "items": [
                        {
                            "title": str(item.get("title") or "Untitled"),
                            "description": "",
                            "meta": str(item.get("year") or ""),
                            "badge": str(item.get("citations") or ""),
                        }
                        for item in stats["top_cited"][:6]
                        if isinstance(item, dict)
                    ],
                },
            )
        recommendations = stats.get("smart_recommendations") or stats.get("recommended_actions")
        if isinstance(recommendations, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "recommendations",
                    "kind": "list",
                    "title": "建议动作",
                    "items": [
                        {"title": str(item), "description": ""}
                        for item in recommendations[:6]
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="文献盘点完成",
            description="已完成统计分析并生成建议动作。",
            tone="success" if stats.get("generation_mode") == "llm" else "warning",
        )
        await _emit_bound_runtime(
            message="正在整理文献盘点产物...",
            current_phase="finalize",
            stage_transition=True,
        )
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
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """LLM-powered literature analysis. Returns None on failure."""
    if not literature:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
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
