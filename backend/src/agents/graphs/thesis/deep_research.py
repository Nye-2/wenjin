"""Deep Research sub-graph — LLM-powered parallel pipeline with cross-validation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.academic.literature.search_service import LiteratureSearchService
from src.agents.feature_leader.graph_registry import register_feature_graph
from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.database import get_db_session
from src.models.router import route_model, validate_requested_model
from src.services.references import ReferenceImportService
from src.task.progress import get_runtime_state
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    upsert_runtime_block,
)
from src.task.runtime_blocks import (
    emit_bound_runtime as _emit_bound_runtime,
)
from src.workspace_features.services.llm_json import (
    build_json_prompt,
    invoke_json_chat_model,
    parse_json_array,
    parse_json_payload,
)

logger = logging.getLogger(__name__)


def _resolve_research_model(requested_model: str | None) -> str:
    """Resolve a chat/research model for deep-research tasks."""
    requested = validate_requested_model(
        requested_model,
        allowed_categories=("llm"),
        require_tools=False,
    )
    return route_model(
        requested_model=requested,
        preferred_categories=("llm",),
        allowed_categories=("llm",),
        require_tools=False,
    )


def _combine_verified_discovery_papers(discovery: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge Semantic Scholar verified works into a deduplicated reference list."""
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    verified = discovery.get("verified_papers")
    if isinstance(verified, list):
        sources = [verified]
    else:
        sources = [
            discovery.get("seminal_works"),
            discovery.get("recent_works"),
        ]

    for works in sources:
        if not isinstance(works, list):
            continue
        for item in works:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            year = str(item.get("year") or "").strip()
            external_id = str(item.get("external_id") or "").strip()
            doi = str(item.get("doi") or "").strip().lower()
            dedupe_key = doi or external_id or f"{title.lower()}::{year}"
            if not title or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            merged.append(item)

    return merged


def _build_recommended_actions(
    *,
    gap_count: int,
    idea_count: int,
) -> list[dict[str, str]]:
    """Produce lightweight next-step recommendations for downstream modules."""
    actions = [
        {
            "action": "literature_management",
            "reason": "先将调研结果沉淀为可筛选、可导入的文献清单。",
        }
    ]

    if gap_count > 0 or idea_count > 0:
        actions.append(
            {
                "action": "thesis_writing.generate_outline",
                "reason": "基于研究空白与候选创意生成论文大纲。",
            }
        )

    if idea_count > 0:
        actions.append(
            {
                "action": "opening_research",
                "reason": "将调研发现转为开题背景、意义与可行性分析。",
            }
        )

    return actions


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("deep_research", workspace_type="thesis")
async def deep_research_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute 4-phase deep research pipeline.

    Pipeline:
        Phase 1 (parallel): Scout Seminal + Scout Recent + Trend Analysis
        Phase 2 (sequential): Gap Mining (uses Phase 1 results)
        Phase 3 (sequential): Synthesis (uses Phase 1 + Phase 2 results)
        Phase 4 (sequential): Cross-Validation (verifies synthesis quality)

    Each phase has LLM fallback. Output combined into structured result payload.
    """
    workspace_id = str(payload.get("workspace_id") or "").strip()
    params = _read_payload_params(payload)
    topic = str(
        params.get("topic")
        or params.get("query")
        or payload.get("workspace_name", "")
    ).strip()
    if not topic:
        topic = "未命名研究主题"
    discipline = str(params.get("discipline", payload.get("workspace_discipline", ""))).strip()
    if not discipline:
        discipline = "通用学科"
    focus_areas: list[str] = params.get("focus_areas", [])
    memory_context = initial_state.get("memory_context")
    requested_model = _read_optional_str(params.get("model_id"))
    model_id = _resolve_research_model(requested_model)
    runtime = get_runtime_state()

    pipeline_steps: dict[str, bool] = {
        "discovery": False,
        "gap_mining": False,
        "synthesis": False,
        "cross_validation": False,
    }

    if runtime is not None:
        append_runtime_activity(
            runtime,
            title="调研任务启动",
            description="开始并行检索经典文献、近期文献与研究趋势。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在发现经典文献、近期工作与研究趋势...",
            current_phase="discovery",
            stage_transition=True,
        )

    # Phase 1: Discovery (parallel)
    discovery = await _phase1_discovery(
        topic,
        discipline,
        focus_areas,
        memory_context,
        workspace_id=workspace_id or None,
        model_id=model_id,
    )
    pipeline_steps["discovery"] = bool(
        discovery.get("verified_papers")
        or discovery.get("seminal_works")
        or discovery.get("recent_works")
        or discovery.get("trends")
    )
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "discovery-summary",
                "kind": "metrics",
                "title": "发现摘要",
                "entries": [
                    {
                        "label": "经典/基础文献",
                        "value": str(
                            len(discovery.get("seminal_works"))
                            if isinstance(discovery.get("seminal_works"), list)
                            else 0
                        ),
                    },
                    {
                        "label": "近期文献",
                        "value": str(
                            len(discovery.get("recent_works"))
                            if isinstance(discovery.get("recent_works"), list)
                            else 0
                        ),
                    },
                    {
                        "label": "已验证文献",
                        "value": str(
                            len(discovery.get("verified_papers"))
                            if isinstance(discovery.get("verified_papers"), list)
                            else 0
                        ),
                    },
                    {
                        "label": "研究趋势",
                        "value": str(
                            len(discovery.get("trends"))
                            if isinstance(discovery.get("trends"), list)
                            else 0
                        ),
                    },
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="文献发现完成",
            description="已完成发现阶段，开始识别研究空白。",
            tone="success" if pipeline_steps["discovery"] else "warning",
        )
        advance_runtime_phase(runtime, "discovery", "gap_mining")
        await _emit_bound_runtime(
            message="正在分析研究空白与问题空间...",
            current_phase="gap_mining",
            stage_transition=True,
        )

    # Phase 2: Gap Mining (sequential, depends on Phase 1)
    gaps = await _phase2_gap_mining(
        discovery,
        topic,
        discipline,
        memory_context,
        model_id=model_id,
    )
    pipeline_steps["gap_mining"] = bool(gaps)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "research-gaps",
                "kind": "list",
                "title": "研究空白",
                "items": [
                    {
                        "title": str(item.get("description") or "研究空白"),
                        "description": str(item.get("potential_impact") or ""),
                        "meta": str(item.get("severity") or ""),
                    }
                    for item in gaps[:6]
                    if isinstance(item, dict)
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="空白识别完成",
            description="已归纳研究空白，开始生成候选研究创意。",
            tone="success" if pipeline_steps["gap_mining"] else "warning",
        )
        advance_runtime_phase(runtime, "gap_mining", "synthesis")
        await _emit_bound_runtime(
            message="正在综合文献与空白生成研究创意...",
            current_phase="synthesis",
            stage_transition=True,
        )

    # Phase 3: Synthesis (sequential, depends on Phase 1 + Phase 2)
    ideas = await _phase3_synthesis(
        discovery,
        gaps,
        topic,
        discipline,
        memory_context,
        model_id=model_id,
    )
    pipeline_steps["synthesis"] = bool(ideas)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "research-ideas",
                "kind": "list",
                "title": "研究创意",
                "items": [
                    {
                        "title": str(item.get("title") or "研究创意"),
                        "description": str(item.get("description") or ""),
                        "meta": str(item.get("novelty_assessment") or ""),
                    }
                    for item in ideas[:6]
                    if isinstance(item, dict)
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="创意综合完成",
            description="已形成候选研究方向，开始执行交叉验证。",
            tone="success" if pipeline_steps["synthesis"] else "warning",
        )
        advance_runtime_phase(runtime, "synthesis", "cross_validation")
        await _emit_bound_runtime(
            message="正在验证发现结果与研究创意的一致性...",
            current_phase="cross_validation",
            stage_transition=True,
        )

    # Phase 4: Cross-Validation (sequential, depends on all above)
    cross_validation = await _phase4_cross_validate(
        discovery,
        gaps,
        ideas,
        topic,
        model_id=model_id,
    )
    pipeline_steps["cross_validation"] = cross_validation is not None
    if runtime is not None:
        if cross_validation is not None:
            upsert_runtime_block(
                runtime,
                {
                    "id": "cross-validation",
                    "kind": "metrics",
                    "title": "交叉验证",
                    "entries": [
                        {
                            "label": "验证评分",
                            "value": str(cross_validation.get("validation_score") or 0),
                        },
                        {
                            "label": "一致性问题",
                            "value": str(
                                len(cross_validation.get("consistency_issues"))
                                if isinstance(cross_validation.get("consistency_issues"), list)
                                else 0
                            ),
                        },
                        {
                            "label": "改进建议",
                            "value": str(
                                len(cross_validation.get("recommendations"))
                                if isinstance(cross_validation.get("recommendations"), list)
                                else 0
                            ),
                        },
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="交叉验证完成",
            description="已完成一致性检查，正在整理最终调研报告。",
            tone="success" if pipeline_steps["cross_validation"] else "warning",
        )
        advance_runtime_phase(runtime, "cross_validation", "finalize")
        await _emit_bound_runtime(
            message="正在整理深度调研报告...",
            current_phase="finalize",
            stage_transition=True,
        )

    verified_papers = _combine_verified_discovery_papers(discovery)

    return {
        "schema_version": "v1",
        "source_feature": "deep_research",
        "source": "semantic_scholar",
        "topic": topic,
        "discipline": discipline,
        "query": {
            "keywords": [topic],
            "focus_areas": focus_areas,
            "constraints": [],
        },
        "corpus": {
            "verified_count": len(verified_papers),
            "verified_papers": verified_papers[:12],
            "retrieval": discovery.get("retrieval") if isinstance(discovery.get("retrieval"), dict) else {},
        },
        "verified_papers": verified_papers,
        "discovery": discovery,
        "gaps": gaps,
        "ideas": ideas,
        "recommended_actions": _build_recommended_actions(
            gap_count=len(gaps),
            idea_count=len(ideas),
        ),
        "cross_validation": cross_validation,
        "reference_import": discovery.get("reference_import")
        if isinstance(discovery.get("reference_import"), dict)
        else {"imported": 0, "created": 0, "items": []},
        "model_id": model_id,
        "pipeline_steps": pipeline_steps,
        "generation_mode": _determine_generation_mode(pipeline_steps),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Phase 1: Discovery (parallel fan-out)
# ---------------------------------------------------------------------------
async def _phase1_discovery(
    topic: str,
    discipline: str,
    focus_areas: list[str],
    memory_context: str | None,
    *,
    workspace_id: str | None = None,
    model_id: str = "default",
) -> dict[str, Any]:
    """Run Semantic Scholar retrieval and trend analysis in parallel."""
    seminal_query = _build_semantic_scholar_query(
        topic=topic,
        discipline=discipline,
        focus_areas=focus_areas,
        intent="foundational seminal key works",
    )
    recent_query = _build_semantic_scholar_query(
        topic=topic,
        discipline=discipline,
        focus_areas=focus_areas,
        intent="recent advances current research",
    )
    results = await asyncio.gather(
        _search_semantic_scholar_verified(seminal_query, discipline=discipline, limit=8),
        _search_semantic_scholar_verified(recent_query, discipline=discipline, limit=8),
        _analyze_trends(topic, discipline, focus_areas, memory_context, model_id=model_id),
        return_exceptions=True,
    )

    seminal_result = results[0] if not isinstance(results[0], BaseException) else {}
    recent_result = results[1] if not isinstance(results[1], BaseException) else {}
    trends = results[2] if not isinstance(results[2], BaseException) else []

    # Log any exceptions from parallel tasks
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            task_names = ["semantic_seminal", "semantic_recent", "analyze_trends"]
            logger.warning("Phase 1 task %s failed: %s", task_names[i], r)

    seminal_papers = (
        seminal_result.get("verified_papers")
        if isinstance(seminal_result, dict) and isinstance(seminal_result.get("verified_papers"), list)
        else []
    )
    recent_papers = (
        recent_result.get("verified_papers")
        if isinstance(recent_result, dict) and isinstance(recent_result.get("verified_papers"), list)
        else []
    )
    verified_papers = _dedupe_verified_papers([*seminal_papers, *recent_papers])
    reference_import = await _import_verified_papers_to_reference_library(
        workspace_id=workspace_id,
        topic=topic,
        verified_papers=verified_papers,
    )

    return {
        "source": "semantic_scholar",
        "seminal_works": _annotate_discovery_papers(seminal_papers, category="seminal"),
        "recent_works": _annotate_discovery_papers(recent_papers, category="recent"),
        "verified_papers": verified_papers,
        "retrieval": _merge_retrieval_info(
            seminal_result if isinstance(seminal_result, dict) else {},
            recent_result if isinstance(recent_result, dict) else {},
        ),
        "reference_import": reference_import,
        "trends": trends if isinstance(trends, list) else [],
    }


# ---------------------------------------------------------------------------
# Phase 1 helpers: Semantic Scholar retrieval / trend LLM calls
# ---------------------------------------------------------------------------
_TREND_ITEM_SCHEMA = """{
  "topic": "趋势主题名称",
  "description": "趋势描述（2-3句话）",
  "growth_direction": "上升/稳定/下降",
  "key_drivers": "推动该趋势的关键因素（1-2句话）"
}"""

_GAP_ITEM_SCHEMA = """{
  "description": "研究空白的详细描述（2-3句话）",
  "supporting_evidence": ["支撑证据1", "支撑证据2"],
  "potential_impact": "填补该空白的潜在学术影响（1-2句话）",
  "severity": "高/中/低"
}"""

_IDEA_ITEM_SCHEMA = """{
  "title": "研究构想标题",
  "description": "构想详细描述（3-5句话）",
  "methodology_hints": ["方法提示1", "方法提示2"],
  "related_gaps": ["对应的研究空白描述"],
  "novelty_assessment": "新颖性评估（1-2句话）"
}"""

_CROSS_VALIDATE_SCHEMA = """{
  "validation_score": 8,
  "consistency_issues": ["一致性问题1（如有）"],
  "quality_notes": ["质量优点1", "质量优点2"],
  "recommendations": ["改进建议1", "改进建议2"]
}"""


def _build_semantic_scholar_query(
    *,
    topic: str,
    discipline: str,
    focus_areas: list[str],
    intent: str,
) -> str:
    """Build a compact Semantic Scholar query from thesis context."""
    parts = [topic, discipline, intent, *[str(item) for item in focus_areas[:5]]]
    normalized = " ".join(" ".join(parts).split()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:240].rstrip() or topic


async def _search_semantic_scholar_verified(
    query: str,
    *,
    discipline: str,
    limit: int = 8,
) -> dict[str, Any]:
    """Retrieve verified papers from the canonical Semantic Scholar service."""
    return await LiteratureSearchService().search(
        query=query,
        discipline=discipline,
        limit=limit,
    )


def _verified_paper_key(paper: dict[str, Any]) -> str:
    doi = str(paper.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    external_id = str(paper.get("external_id") or "").strip()
    if external_id:
        return f"semantic_scholar:{external_id}"
    title = str(paper.get("title") or "").strip().lower()
    year = str(paper.get("year") or "").strip()
    return f"title:{title}:{year}"


def _dedupe_verified_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title") or "").strip()
        if not title:
            continue
        key = _verified_paper_key(paper)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    return deduped


def _annotate_discovery_papers(
    papers: list[dict[str, Any]],
    *,
    category: str,
) -> list[dict[str, Any]]:
    """Project verified paper metadata into discovery-summary records."""
    label = "Semantic Scholar 经典/基础检索命中" if category == "seminal" else "Semantic Scholar 近期研究检索命中"
    annotated: list[dict[str, Any]] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title") or "").strip()
        if not title:
            continue
        abstract = " ".join(str(paper.get("abstract") or "").split())
        annotated.append(
            {
                **paper,
                "significance": abstract[:320] or label,
                "relevance": (
                    f"{label}；source=semantic_scholar；"
                    f"external_id={paper.get('external_id') or 'n/a'}"
                ),
                "evidence_source": "semantic_scholar",
            }
        )
    return annotated


def _merge_retrieval_info(*results: dict[str, Any]) -> dict[str, Any]:
    retrievals = [
        item.get("retrieval")
        for item in results
        if isinstance(item, dict) and isinstance(item.get("retrieval"), dict)
    ]
    return {
        "source": "semantic_scholar",
        "queries": [
            {
                "query": retrieval.get("query"),
                "status": retrieval.get("status"),
                "returned": retrieval.get("returned"),
                "verified": retrieval.get("verified"),
                "error": retrieval.get("error"),
                "verified_at": retrieval.get("verified_at"),
            }
            for retrieval in retrievals
        ],
        "verified": sum(int(retrieval.get("verified") or 0) for retrieval in retrievals),
        "status": "ok" if retrievals and all(retrieval.get("status") == "ok" for retrieval in retrievals) else "partial",
        "verified_at": next((retrieval.get("verified_at") for retrieval in retrievals if retrieval.get("verified_at")), None),
    }


async def _import_verified_papers_to_reference_library(
    *,
    workspace_id: str | None,
    topic: str,
    verified_papers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist verified deep-research papers into the workspace Reference Library."""
    if not workspace_id or not verified_papers:
        return {"imported": 0, "created": 0, "items": []}
    try:
        async with get_db_session() as db:
            return await ReferenceImportService(db).import_semantic_scholar_papers(
                workspace_id=workspace_id,
                papers=verified_papers,
                source_label=f"Deep research: {topic}",
            )
    except Exception as exc:
        logger.warning(
            "Failed to import deep research verified papers into Reference Library for workspace=%s: %s",
            workspace_id,
            exc,
            exc_info=True,
        )
        return {"imported": 0, "created": 0, "items": [], "error": str(exc)}


async def _analyze_trends(
    topic: str,
    discipline: str,
    focus_areas: list[str],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Analyze current research trends for the topic."""
    prompt = build_json_prompt(
        instruction="请分析当前研究主题的主要趋势，并判断它们是上升、稳定还是下降。",
        context_sections=(
            ("研究主题", topic),
            ("学科方向", discipline),
            ("重点关注方向", focus_areas),
            ("工作记忆", memory_context),
        ),
        schema=f"[{_TREND_ITEM_SCHEMA}]",
        requirements=(
            "趋势要尽量具体到方法、任务、数据或应用方向，不要只写宏观口号。",
            "growth_direction 只能使用“上升”“稳定”“下降”三种值。",
            "key_drivers 要说明趋势背后的方法、数据、评测或应用推动因素。",
        ),
        output_language="中文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的学术趋势分析专家，负责基于可见证据区分上升、稳定和下降方向。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.2,
        expected_type="array",
    )
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if generation_error:
        logger.warning("Analyze trends failed: %s", generation_error)
    return []


async def _phase2_gap_mining(
    discovery_results: dict[str, Any],
    topic: str,
    discipline: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Identify research gaps from discovered works."""
    discovery_summary = _build_discovery_summary(discovery_results)
    prompt = build_json_prompt(
        instruction="请基于已发现的文献和趋势，识别真正值得研究的关键空白。",
        context_sections=(
            ("研究主题", topic),
            ("学科方向", discipline),
            ("已发现文献与趋势摘要", discovery_summary),
            ("工作记忆", memory_context),
        ),
        schema=f"[{_GAP_ITEM_SCHEMA}]",
        requirements=(
            "研究空白应可研究、可验证，避免把“还没看够文献”误写成研究空白。",
            "supporting_evidence 必须尽量从 discovery summary 中抽取可见依据。",
            "severity 只能使用“高”“中”“低”。",
        ),
        output_language="中文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的研究空白分析专家，负责从已发现证据中提炼可研究、可验证的 gap。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.2,
        expected_type="array",
    )
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if generation_error:
        logger.warning("Phase 2 (gap mining) failed: %s", generation_error)
    return []


async def _phase3_synthesis(
    discovery_results: dict[str, Any],
    gaps: list[dict[str, Any]],
    topic: str,
    discipline: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Generate novel research ideas addressing identified gaps."""
    discovery_summary = _build_discovery_summary(discovery_results)
    gaps_text = json.dumps(gaps, ensure_ascii=False, indent=2) if gaps else "（未识别到研究空白）"
    prompt = build_json_prompt(
        instruction="请基于文献、趋势和研究空白，提出少而精、可落地的研究构想。",
        context_sections=(
            ("研究主题", topic),
            ("学科方向", discipline),
            ("已发现文献与趋势摘要", discovery_summary),
            ("已识别研究空白", gaps_text),
            ("工作记忆", memory_context),
        ),
        schema=f"[{_IDEA_ITEM_SCHEMA}]",
        requirements=(
            "研究构想要明确问题、方向和方法提示，避免空泛 brainstorming。",
            "related_gaps 应引用已识别的空白，而不是重新发明一套问题。",
            "novelty_assessment 要诚实评估新颖性边界和潜在风险。",
        ),
        output_language="中文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的学术创新构想专家，负责把已识别 gap 转成少而精、可落地的研究构想。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.25,
        expected_type="array",
    )
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if generation_error:
        logger.warning("Phase 3 (synthesis) failed: %s", generation_error)
    return []


async def _phase4_cross_validate(
    discovery: dict[str, Any],
    gaps: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    topic: str,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Verify synthesis quality and internal consistency. Returns None on failure."""
    discovery_summary = _build_discovery_summary(discovery)
    gaps_text = json.dumps(gaps, ensure_ascii=False, indent=2) if gaps else "（无）"
    ideas_text = json.dumps(ideas, ensure_ascii=False, indent=2) if ideas else "（无）"
    prompt = build_json_prompt(
        instruction="请审查这份深度调研结果的一致性、质量和可执行性。",
        context_sections=(
            ("研究主题", topic),
            ("发现的文献与趋势", discovery_summary),
            ("识别的研究空白", gaps_text),
            ("生成的研究构想", ideas_text),
        ),
        schema=_CROSS_VALIDATE_SCHEMA,
        requirements=(
            "validation_score 必须是 1-10 的整数。",
            "consistency_issues 只列真正会影响可信度的问题；没有则返回空数组。",
            "recommendations 应是下一步可执行的改进建议，不要泛泛而谈。",
        ),
        output_language="中文",
    )
    parsed, _, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的调研质量审核专家，负责检查调研结果的一致性、证据边界和可执行性。",
        prompt=prompt,
        resolved_model_id=model_id,
        temperature=0.2,
    )
    if isinstance(parsed, dict):
        return parsed
    if generation_error:
        logger.warning("Phase 4 (cross-validation) failed: %s", generation_error)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Compatibility wrapper for tests around JSON parsing behavior."""
    return parse_json_payload(text)


def _parse_json_list_response(text: str) -> list[dict[str, Any]] | None:
    """Compatibility wrapper for tests around JSON list parsing behavior."""
    return parse_json_array(text)


def _build_discovery_summary(discovery: dict[str, Any], max_items: int = 10) -> str:
    """Format discovery results for inclusion in later LLM prompts (truncated)."""
    parts: list[str] = []

    seminal = discovery.get("seminal_works", [])
    if seminal:
        parts.append("经典文献:")
        for item in seminal[:max_items]:
            title = item.get("title", "未知")
            year = item.get("year", "")
            significance = item.get("significance", "")
            parts.append(f"  - {title} ({year}): {significance}")

    recent = discovery.get("recent_works", [])
    if recent:
        parts.append("近期文献:")
        for item in recent[:max_items]:
            title = item.get("title", "未知")
            year = item.get("year", "")
            significance = item.get("significance", "")
            parts.append(f"  - {title} ({year}): {significance}")

    trends = discovery.get("trends", [])
    if trends:
        parts.append("研究趋势:")
        for item in trends[:max_items]:
            topic_name = item.get("topic", "未知")
            description = item.get("description", "")
            parts.append(f"  - {topic_name}: {description}")

    return "\n".join(parts) if parts else "（暂无发现结果）"


def _determine_generation_mode(steps: dict[str, bool]) -> str:
    """Compute generation mode from pipeline steps results."""
    if not steps:
        return "failed"
    succeeded = sum(steps.values())
    total = len(steps)
    if succeeded == total:
        return "llm"
    elif succeeded > 0:
        return "partial_llm"
    else:
        return "failed"
