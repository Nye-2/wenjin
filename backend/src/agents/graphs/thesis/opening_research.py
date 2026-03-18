"""Opening Research sub-graph — 3-step LLM pipeline for opening reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.graphs._shared import _read_optional_str
from src.agents.workspace_lead_agent import register_feature_graph
from src.models.router import route_writing_model

logger = logging.getLogger(__name__)


def _resolve_writing_model(requested_model: str | None) -> str:
    """Resolve a writing model with safe fallback."""
    try:
        return route_writing_model(requested_model=requested_model)
    except Exception:
        return requested_model or "default"

# ---------------------------------------------------------------------------
# Report type constants
# ---------------------------------------------------------------------------
_REPORT_TYPES = {"opening_report", "literature_review", "feasibility_analysis"}


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("opening_research", workspace_type="thesis")
async def opening_research_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute 3-step opening research pipeline.

    Pipeline:
        1. analyze_research_status — Analyze research landscape
        2. plan_methodology — Plan research methodology
        3. generate_report_sections — Generate report sections

    Each step has template fallback. Output combined into artifact payload.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = payload.get("params", {})
    topic = str(params.get("topic", payload.get("workspace_name", "未命名研究主题"))).strip()
    if not topic:
        topic = "未命名研究主题"
    report_type = _normalize_report_type(str(params.get("report_type", "opening_report")))
    workspace_description = str(payload.get("workspace_description", ""))
    memory_context = initial_state.get("knowledge_context")
    requested_model = _read_optional_str(params.get("model_id"))
    model_id = _resolve_writing_model(requested_model)

    # Step 0: Load literature
    literature = await _load_literature(workspace_id)
    literature_highlights = _build_literature_highlights(literature)

    # Step 1: Analyze research status
    research_analysis = await _analyze_research_status(
        literature=literature,
        focus_topic=topic,
        memory_context=memory_context,
        model_id=model_id,
    )

    # Step 2: Plan methodology
    methodology_plan = await _plan_methodology(
        research_analysis=research_analysis,
        report_type=report_type,
        topic=topic,
        model_id=model_id,
    )

    # Step 3: Generate report sections
    sections = await _generate_report_sections(
        research_analysis=research_analysis,
        methodology_plan=methodology_plan,
        report_type=report_type,
        topic=topic,
        workspace_description=workspace_description,
        literature_highlights=literature_highlights,
        memory_context=memory_context,
        model_id=model_id,
    )

    # Determine generation mode
    step_results = {
        "status_analysis": research_analysis is not None,
        "methodology_planning": methodology_plan is not None,
        "section_generation": any(s.get("source") == "llm" for s in sections),
    }
    succeeded = sum(step_results.values())
    if succeeded == 3:
        generation_mode = "llm"
    elif succeeded > 0:
        generation_mode = "partial_llm"
    else:
        generation_mode = "template_fallback"

    return {
        "topic": topic,
        "report_type": report_type,
        "sections": sections,
        "research_analysis": research_analysis,
        "methodology_plan": methodology_plan,
        "reference_clues": literature_highlights,
        "literature_count": len(literature),
        "model_id": model_id,
        "generation_mode": generation_mode,
        "pipeline_steps": step_results,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Helper: normalize report type
# ---------------------------------------------------------------------------
def _normalize_report_type(report_type: str) -> str:
    normalized = (report_type or "").strip().lower()
    if normalized not in _REPORT_TYPES:
        return "opening_report"
    return normalized


# ---------------------------------------------------------------------------
# Helper: load literature from DB
# ---------------------------------------------------------------------------
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
        logger.exception("Failed to load literature for opening research")
        return []


# ---------------------------------------------------------------------------
# Helper: build literature highlights
# ---------------------------------------------------------------------------
def _build_literature_highlights(literature: list[dict[str, Any]], max_items: int = 8) -> list[str]:
    """Extract title(year) - venue strings for reference clues."""
    highlights: list[str] = []
    for item in literature[:max_items]:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        year = item.get("year")
        venue = str(item.get("venue") or "").strip()
        year_part = f"({year})" if year else ""
        venue_part = f" - {venue}" if venue else ""
        highlights.append(f"{title}{year_part}{venue_part}")
    return highlights


# ---------------------------------------------------------------------------
# Helper: build template sections (fallback)
# ---------------------------------------------------------------------------
def _build_template_sections(
    report_type: str,
    topic: str,
    workspace_description: str,
    literature_highlights: list[str],
) -> list[dict[str, str]]:
    """Build template sections for each report type — used as LLM fallback."""
    if report_type == "literature_review":
        sections = [
            {
                "title": "检索范围与方法",
                "content": (
                    f"围绕\u201c{topic}\u201d设定检索范围，优先覆盖近5年高相关文献；"
                    "使用关键词组合、前向/后向追踪与主题聚类进行筛选。"
                ),
            },
            {
                "title": "代表性研究脉络",
                "content": "从方法路线、数据条件与评价指标三个维度梳理主流研究脉络。",
            },
            {
                "title": "关键文献评述",
                "content": "比较代表性工作的创新点、局限性与可复现性，提炼可借鉴策略。",
            },
            {
                "title": "研究空白与切入点",
                "content": "结合现有成果缺口提出可执行的论文切入点，并说明预期贡献。",
            },
        ]
    elif report_type == "feasibility_analysis":
        sections = [
            {
                "title": "研究目标与约束条件",
                "content": f"研究主题为\u201c{topic}\u201d，需在现有时间、算力和数据条件下完成可验证结论。",
            },
            {
                "title": "技术可行性",
                "content": "评估核心方法的实现复杂度、工程风险和替代技术方案。",
            },
            {
                "title": "资源与数据可行性",
                "content": "确认数据来源、标注成本与实验环境，确保复现实验链路可运行。",
            },
            {
                "title": "计划与风险控制",
                "content": "给出里程碑计划、关键风险清单及相应的降级与兜底方案。",
            },
        ]
    else:
        # opening_report (default)
        sections = [
            {
                "title": "研究背景与意义",
                "content": (
                    f"围绕\u201c{topic}\u201d阐述问题背景与研究价值。"
                    f"{workspace_description or '结合所在领域实践需求，明确研究动机。'}"
                ),
            },
            {
                "title": "国内外研究现状",
                "content": "从主流方法、数据基础和评测方式三个方面总结研究现状。",
            },
            {
                "title": "研究目标与主要内容",
                "content": "明确论文研究目标、关键问题定义及章节级研究内容。",
            },
            {
                "title": "技术路线与方法设计",
                "content": "说明从问题建模、方法实现到实验验证的完整技术路线。",
            },
            {
                "title": "创新点与预期成果",
                "content": "提炼可验证创新点并定义预期论文产出与评估指标。",
            },
            {
                "title": "进度安排与风险预案",
                "content": "按阶段给出里程碑计划，并补充关键风险和应对策略。",
            },
        ]

    if literature_highlights:
        sections.append(
            {
                "title": "参考文献线索",
                "content": "核心参考：\n" + "\n".join(f"- {item}" for item in literature_highlights[:6]),
            }
        )
    return sections


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


# ---------------------------------------------------------------------------
# Helper: build literature summary text for LLM prompts
# ---------------------------------------------------------------------------
def _build_literature_summary(literature: list[dict[str, Any]], max_items: int = 30) -> str:
    """Build a text summary of literature for use in LLM prompts."""
    summaries: list[str] = []
    for p in literature[:max_items]:
        title = p.get("title", "Unknown")
        year = p.get("year", "")
        citations = p.get("citations", 0)
        abstract = (p.get("abstract") or "")[:200]
        summaries.append(f"- {title} ({year}, cited {citations}x): {abstract}")
    return "\n".join(summaries) if summaries else "（暂无文献）"


# ---------------------------------------------------------------------------
# LLM Step 1: Analyze research status
# ---------------------------------------------------------------------------
_STEP1_PROMPT = """你是学术研究分析专家。基于以下文献列表和研究方向，分析当前研究现状。

研究方向: {topic}

文献列表:
{literature_summary}
{memory_context}

请分析并返回 JSON:
{{
  "research_status": "对该领域当前研究状态的概述（3-5句话）",
  "key_trends": ["趋势1", "趋势2", "趋势3"],
  "research_gaps": ["研究空白1", "研究空白2"],
  "theoretical_foundations": ["理论基础1", "理论基础2"]
}}

仅返回 JSON。"""


async def _analyze_research_status(
    literature: list[dict[str, Any]],
    focus_topic: str,
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Step 1: LLM analyzes research landscape. Returns None on failure."""
    if not literature:
        return None

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    lit_text = _build_literature_summary(literature)
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _STEP1_PROMPT.format(
        topic=focus_topic,
        literature_summary=lit_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("Step 1 (analyze_research_status) failed")
        return None


# ---------------------------------------------------------------------------
# LLM Step 2: Plan methodology
# ---------------------------------------------------------------------------
_STEP2_PROMPT = """你是学术方法论规划专家。基于前一步的研究现状分析，为以下报告类型规划研究方法。

报告类型: {report_type}
研究方向: {topic}

研究现状分析:
{research_analysis}

请规划并返回 JSON:
{{
  "objectives": ["研究目标1", "研究目标2", "研究目标3"],
  "methodology": "研究方法论概述（3-5句话）",
  "technical_approach": "技术路线概述（3-5句话）",
  "innovation_points": ["创新点1", "创新点2"]
}}

仅返回 JSON。"""


async def _plan_methodology(
    research_analysis: dict[str, Any] | None,
    report_type: str,
    topic: str,
    *,
    model_id: str = "default",
) -> dict[str, Any] | None:
    """Step 2: LLM plans research methodology. Returns None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return None

    analysis_text = json.dumps(research_analysis, ensure_ascii=False, indent=2) if research_analysis else "（前一步分析未生成，请基于通用学术方法论进行规划）"

    prompt = _STEP2_PROMPT.format(
        report_type=report_type,
        topic=topic,
        research_analysis=analysis_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("Step 2 (plan_methodology) failed")
        return None


# ---------------------------------------------------------------------------
# LLM Step 3: Generate report sections
# ---------------------------------------------------------------------------
_STEP3_PROMPT = """你是学术报告撰写专家。基于研究分析和方法论规划，生成完整的报告章节。

报告类型: {report_type}
研究方向: {topic}

研究现状分析:
{research_analysis}

方法论规划:
{methodology_plan}

参考文献线索:
{literature_highlights}
{memory_context}

请按照以下结构生成报告章节，返回 JSON 列表:
{section_schema}

每个章节格式: {{"title": "章节标题", "content": "章节详细内容（200-500字）"}}

仅返回 JSON 列表。"""

_SECTION_SCHEMAS: dict[str, str] = {
    "opening_report": """[
  {{"title": "研究背景与意义", "content": "..."}},
  {{"title": "国内外研究现状", "content": "..."}},
  {{"title": "研究目标与主要内容", "content": "..."}},
  {{"title": "技术路线与方法设计", "content": "..."}},
  {{"title": "创新点与预期成果", "content": "..."}},
  {{"title": "进度安排与风险预案", "content": "..."}}
]""",
    "literature_review": """[
  {{"title": "检索范围与方法", "content": "..."}},
  {{"title": "代表性研究脉络", "content": "..."}},
  {{"title": "关键文献评述", "content": "..."}},
  {{"title": "研究空白与切入点", "content": "..."}}
]""",
    "feasibility_analysis": """[
  {{"title": "研究目标与约束条件", "content": "..."}},
  {{"title": "技术可行性", "content": "..."}},
  {{"title": "资源与数据可行性", "content": "..."}},
  {{"title": "计划与风险控制", "content": "..."}}
]""",
}


async def _generate_report_sections(
    research_analysis: dict[str, Any] | None,
    methodology_plan: dict[str, Any] | None,
    report_type: str,
    topic: str,
    workspace_description: str,
    literature_highlights: list[str],
    memory_context: str | None,
    *,
    model_id: str = "default",
) -> list[dict[str, Any]]:
    """Step 3: LLM generates full report sections. Falls back to template."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model(model_id, temperature=0.3)
    except Exception:
        return _fallback_template_sections(report_type, topic, workspace_description, literature_highlights)

    analysis_text = (
        json.dumps(research_analysis, ensure_ascii=False, indent=2)
        if research_analysis
        else "（未生成）"
    )
    methodology_text = (
        json.dumps(methodology_plan, ensure_ascii=False, indent=2)
        if methodology_plan
        else "（未生成）"
    )
    lit_text = "\n".join(f"- {h}" for h in literature_highlights) if literature_highlights else "（暂无）"
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""
    section_schema = _SECTION_SCHEMAS.get(report_type, _SECTION_SCHEMAS["opening_report"])

    prompt = _STEP3_PROMPT.format(
        report_type=report_type,
        topic=topic,
        research_analysis=analysis_text,
        methodology_plan=methodology_text,
        literature_highlights=lit_text,
        memory_context=mem_text,
        section_schema=section_schema,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_list_response(content)
        if parsed and len(parsed) >= 2:
            return [
                {"title": s.get("title", ""), "content": s.get("content", ""), "source": "llm"}
                for s in parsed
            ]
    except Exception:
        logger.exception("Step 3 (generate_report_sections) failed")

    return _fallback_template_sections(report_type, topic, workspace_description, literature_highlights)


def _fallback_template_sections(
    report_type: str,
    topic: str,
    workspace_description: str,
    literature_highlights: list[str],
) -> list[dict[str, Any]]:
    """Wrap template sections with source='template'."""
    raw = _build_template_sections(report_type, topic, workspace_description, literature_highlights)
    return [
        {"title": s["title"], "content": s["content"], "source": "template"}
        for s in raw
    ]
