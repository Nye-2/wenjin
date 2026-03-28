"""Deep Research sub-graph — LLM-powered parallel pipeline with cross-validation."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.models.router import route_model, validate_requested_model
from src.task.progress import get_runtime_state
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    emit_bound_runtime as _emit_bound_runtime,
    runtime_progress_for_phase,
    upsert_runtime_block,
)

logger = logging.getLogger(__name__)


def _resolve_research_model(requested_model: str | None) -> str:
    """Resolve a chat/research model for deep-research tasks."""
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


def _combine_discovery_papers(discovery: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge seminal and recent works into a deduplicated paper list."""
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for key in ("seminal_works", "recent_works"):
        works = discovery.get(key)
        if not isinstance(works, list):
            continue
        for item in works:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            year = str(item.get("year") or "").strip()
            dedupe_key = f"{title.lower()}::{year}"
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
        model_id=model_id,
    )
    pipeline_steps["discovery"] = bool(
        discovery.get("seminal_works")
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
                        "label": "经典文献",
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

    papers = _combine_discovery_papers(discovery)

    return {
        "schema_version": "v1",
        "source_feature": "deep_research",
        "topic": topic,
        "discipline": discipline,
        "query": {
            "keywords": [topic],
            "focus_areas": focus_areas,
            "constraints": [],
        },
        "corpus": {
            "paper_count": len(papers),
            "top_papers": papers[:8],
        },
        "discovery": discovery,
        "gaps": gaps,
        "ideas": ideas,
        "recommended_actions": _build_recommended_actions(
            gap_count=len(gaps),
            idea_count=len(ideas),
        ),
        "cross_validation": cross_validation,
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
    model_id: str = "default",
) -> dict[str, Any]:
    """Run 3 discovery tasks in parallel via asyncio.gather."""
    results = await asyncio.gather(
        _scout_seminal_works(topic, discipline, focus_areas, memory_context, model_id=model_id),
        _scout_recent_works(topic, discipline, focus_areas, memory_context, model_id=model_id),
        _analyze_trends(topic, discipline, focus_areas, memory_context, model_id=model_id),
        return_exceptions=True,
    )

    seminal = results[0] if not isinstance(results[0], BaseException) else []
    recent = results[1] if not isinstance(results[1], BaseException) else []
    trends = results[2] if not isinstance(results[2], BaseException) else []

    # Log any exceptions from parallel tasks
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            task_names = ["scout_seminal", "scout_recent", "analyze_trends"]
            logger.warning("Phase 1 task %s failed: %s", task_names[i], r)

    return {
        "seminal_works": seminal if isinstance(seminal, list) else [],
        "recent_works": recent if isinstance(recent, list) else [],
        "trends": trends if isinstance(trends, list) else [],
    }


# ---------------------------------------------------------------------------
# Phase 1 helpers: individual scout / trend LLM calls
# ---------------------------------------------------------------------------
_SCOUT_SEMINAL_PROMPT = """你是学术文献发现专家。请针对以下研究主题识别该领域的经典开创性文献。

研究主题: {topic}
学科方向: {discipline}
{focus_areas_text}
{memory_context}

请识别 5-8 篇该领域最重要的经典/开创性文献，返回 JSON 列表:
[
  {{
    "title": "论文标题",
    "authors": "主要作者（简写）",
    "year": 2020,
    "significance": "该文献的学术贡献和影响（1-2句话）",
    "relevance": "与当前研究主题的关联（1句话）"
  }}
]

仅返回 JSON 列表。"""


async def _scout_seminal_works(
    topic: str,
    discipline: str,
    focus_areas: list[str],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Identify seminal/foundational works for the topic."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return []

    focus_text = f"\n重点关注方向: {', '.join(focus_areas)}" if focus_areas else ""
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _SCOUT_SEMINAL_PROMPT.format(
        topic=topic,
        discipline=discipline,
        focus_areas_text=focus_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_list_response(content) or []
    except Exception:
        logger.exception("Scout seminal works failed")
        return []


_SCOUT_RECENT_PROMPT = """你是学术文献发现专家。请针对以下研究主题识别近2-3年内的最新重要文献。

研究主题: {topic}
学科方向: {discipline}
{focus_areas_text}
{memory_context}

请识别 5-8 篇近年来最有影响力的最新文献，返回 JSON 列表:
[
  {{
    "title": "论文标题",
    "authors": "主要作者（简写）",
    "year": 2024,
    "significance": "该文献的学术贡献和创新点（1-2句话）",
    "relevance": "与当前研究主题的关联（1句话）"
  }}
]

仅返回 JSON 列表。"""


async def _scout_recent_works(
    topic: str,
    discipline: str,
    focus_areas: list[str],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Identify recent cutting-edge works for the topic."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return []

    focus_text = f"\n重点关注方向: {', '.join(focus_areas)}" if focus_areas else ""
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _SCOUT_RECENT_PROMPT.format(
        topic=topic,
        discipline=discipline,
        focus_areas_text=focus_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_list_response(content) or []
    except Exception:
        logger.exception("Scout recent works failed")
        return []


_ANALYZE_TRENDS_PROMPT = """你是学术趋势分析专家。请分析以下研究主题的当前研究趋势。

研究主题: {topic}
学科方向: {discipline}
{focus_areas_text}
{memory_context}

请分析 3-5 个主要研究趋势，返回 JSON 列表:
[
  {{
    "topic": "趋势主题名称",
    "description": "趋势描述（2-3句话）",
    "growth_direction": "上升/稳定/下降",
    "key_drivers": "推动该趋势的关键因素（1-2句话）"
  }}
]

仅返回 JSON 列表。"""


async def _analyze_trends(
    topic: str,
    discipline: str,
    focus_areas: list[str],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Analyze current research trends for the topic."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return []

    focus_text = f"\n重点关注方向: {', '.join(focus_areas)}" if focus_areas else ""
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _ANALYZE_TRENDS_PROMPT.format(
        topic=topic,
        discipline=discipline,
        focus_areas_text=focus_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_list_response(content) or []
    except Exception:
        logger.exception("Analyze trends failed")
        return []


# ---------------------------------------------------------------------------
# Phase 2: Gap Mining
# ---------------------------------------------------------------------------
_GAP_MINING_PROMPT = """你是研究空白分析专家。基于以下发现的文献和趋势，识别该领域的研究空白。

研究主题: {topic}
学科方向: {discipline}

已发现文献与趋势摘要:
{discovery_summary}
{memory_context}

请识别 3-5 个重要的研究空白，返回 JSON 列表:
[
  {{
    "description": "研究空白的详细描述（2-3句话）",
    "supporting_evidence": ["支撑证据1", "支撑证据2"],
    "potential_impact": "填补该空白的潜在学术影响（1-2句话）",
    "severity": "高/中/低"
  }}
]

仅返回 JSON 列表。"""


async def _phase2_gap_mining(
    discovery_results: dict[str, Any],
    topic: str,
    discipline: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Identify research gaps from discovered works."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return []

    discovery_summary = _build_discovery_summary(discovery_results)
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _GAP_MINING_PROMPT.format(
        topic=topic,
        discipline=discipline,
        discovery_summary=discovery_summary,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_list_response(content) or []
    except Exception:
        logger.exception("Phase 2 (gap mining) failed")
        return []


# ---------------------------------------------------------------------------
# Phase 3: Synthesis
# ---------------------------------------------------------------------------
_SYNTHESIS_PROMPT = """你是学术创新构想专家。基于已发现的文献、趋势和研究空白，生成新颖的研究思路。

研究主题: {topic}
学科方向: {discipline}

已发现文献与趋势摘要:
{discovery_summary}

已识别研究空白:
{gaps_summary}
{memory_context}

请生成 2-3 个新颖的研究构想，返回 JSON 列表:
[
  {{
    "title": "研究构想标题",
    "description": "构想详细描述（3-5句话）",
    "methodology_hints": ["方法提示1", "方法提示2"],
    "related_gaps": ["对应的研究空白描述"],
    "novelty_assessment": "新颖性评估（1-2句话）"
  }}
]

仅返回 JSON 列表。"""


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
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return []

    discovery_summary = _build_discovery_summary(discovery_results)
    gaps_text = json.dumps(gaps, ensure_ascii=False, indent=2) if gaps else "（未识别到研究空白）"
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _SYNTHESIS_PROMPT.format(
        topic=topic,
        discipline=discipline,
        discovery_summary=discovery_summary,
        gaps_summary=gaps_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_list_response(content) or []
    except Exception:
        logger.exception("Phase 3 (synthesis) failed")
        return []


# ---------------------------------------------------------------------------
# Phase 4: Cross-Validation (NEW)
# ---------------------------------------------------------------------------
_CROSS_VALIDATE_PROMPT = """你是学术研究质量审核专家。请审查以下深度研究结果的一致性和质量。

研究主题: {topic}

发现的文献与趋势:
{discovery_summary}

识别的研究空白:
{gaps_summary}

生成的研究构想:
{ideas_summary}

请从以下维度审核并返回 JSON:
{{
  "validation_score": 8,
  "consistency_issues": ["一致性问题1（如有）"],
  "quality_notes": ["质量优点1", "质量优点2"],
  "recommendations": ["改进建议1", "改进建议2"]
}}

其中 validation_score 为 1-10 的整数（10 为最高质量）。
仅返回 JSON。"""


async def _phase4_cross_validate(
    discovery: dict[str, Any],
    gaps: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    topic: str,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Verify synthesis quality and internal consistency. Returns None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    discovery_summary = _build_discovery_summary(discovery)
    gaps_text = json.dumps(gaps, ensure_ascii=False, indent=2) if gaps else "（无）"
    ideas_text = json.dumps(ideas, ensure_ascii=False, indent=2) if ideas else "（无）"

    prompt = _CROSS_VALIDATE_PROMPT.format(
        topic=topic,
        discovery_summary=discovery_summary,
        gaps_summary=gaps_text,
        ideas_summary=ideas_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("Phase 4 (cross-validation) failed")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON dict from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_json_list_response(text: str) -> list[dict[str, Any]] | None:
    """Parse JSON list from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            return parsed
        return None
    except json.JSONDecodeError:
        return None


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
