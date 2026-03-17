"""Proposal Outline sub-graph — LLM-powered proposal outline generation.

This module implements the proposal_outline feature using LangGraph pattern:
- Parameter extraction and normalization
- LLM-powered section generation with template fallback
- Milestone and risk planning
- Structured output with generation_mode tracking
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)

PROPOSAL_OUTPUT_LANGUAGE = "zh"

# Proposal types mapping
PROPOSAL_TYPES = {
    "national_natural_science": "国家自然科学基金",
    "national_social_science": "国家社会科学基金",
    "provincial": "省部级项目",
    "enterprise": "企业联合项目",
    "university": "校级项目",
    "other": "其他类型",
}

# Default proposal periods (in months)
DEFAULT_PERIODS = {
    "national_natural_science": 36,
    "national_social_science": 36,
    "provincial": 24,
    "enterprise": 12,
    "university": 12,
    "other": 24,
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_proposal_type(proposal_type: str) -> str:
    """Normalize proposal type to canonical key."""
    normalized = (proposal_type or "").strip().lower().replace(" ", "_")
    # Handle common variations
    mapping = {
        "国自然": "national_natural_science",
        "nsfc": "national_natural_science",
        "国社科": "national_social_science",
        "省部": "provincial",
        "企业": "enterprise",
        "校级": "university",
    }
    for key, value in mapping.items():
        if key in normalized:
            return value
    return normalized if normalized in PROPOSAL_TYPES else "other"


def _normalize_period(period: int | str | None, proposal_type: str) -> int:
    """Normalize period to months."""
    if period is None:
        return DEFAULT_PERIODS.get(proposal_type, 24)
    try:
        return int(period)
    except (TypeError, ValueError):
        return DEFAULT_PERIODS.get(proposal_type, 24)


def _build_schedule_template(period_months: int) -> str:
    """Build schedule template based on period."""
    if period_months <= 12:
        phases = [
            ("第1-3月", "文献调研与方案设计"),
            ("第4-6月", "实验/研究实施"),
            ("第7-9月", "数据分析与结果整理"),
            ("第10-12月", "报告撰写与成果总结"),
        ]
    elif period_months <= 24:
        phases = [
            ("第1-6月", "文献调研与理论准备"),
            ("第7-12月", "实验/研究方案设计与初步实施"),
            ("第13-18月", "深入研究与数据采集"),
            ("第19-24月", "成果整理与报告撰写"),
        ]
    else:
        phases = [
            ("第1年", "文献调研、理论准备与方案设计"),
            ("第2年", "实验/研究实施与数据分析"),
            ("第3年", "深入研究、成果整理与报告撰写"),
        ]

    lines = [f"项目周期：{period_months}个月\n"]
    for period, task in phases:
        lines.append(f"- {period}：{task}")
    return "\n".join(lines)


def _build_proposal_template_sections(
    *,
    topic: str,
    proposal_type: str,
    period_months: int,
) -> list[dict[str, str]]:
    """Build template sections for proposal outline."""
    type_label = PROPOSAL_TYPES.get(proposal_type, "科研项目")

    return [
        {
            "id": "basis",
            "title": "立项依据",
            "content": (
                f"1. 研究意义\n"
                f"阐述\"{topic}\"的研究背景与理论/实践价值，"
                f"说明该研究对学科发展或行业应用的重要意义。\n\n"
                f"2. 国内外研究现状及分析\n"
                f"梳理国内外在相关领域的主要研究进展，"
                f"分析现有研究的优势与不足，找出研究空白。\n\n"
                f"3. 参考文献\n"
                f"列出主要参考文献（建议10-20篇）。"
            ),
        },
        {
            "id": "objectives",
            "title": "研究目标与内容",
            "content": (
                f"1. 研究目标\n"
                f"明确{type_label}的总体目标和具体目标，"
                f"目标应具有可衡量性和可实现性。\n\n"
                f"2. 研究内容\n"
                f"分解为3-5个具体研究内容，"
                f"每个内容应明确研究范围和预期成果。\n\n"
                f"3. 拟解决的关键科学问题\n"
                f"提炼1-3个关键科学问题或技术难题。"
            ),
        },
        {
            "id": "methodology",
            "title": "研究方案与技术路线",
            "content": (
                f"1. 研究方法\n"
                f"说明采用的主要研究方法（理论分析、实验研究、"
                f"数值模拟、调查研究等）及其选择依据。\n\n"
                f"2. 技术路线\n"
                f"描述从问题提出到成果产出的完整技术路径，"
                f"建议配合流程图说明。\n\n"
                f"3. 可行性分析\n"
                f"从理论、技术、资源等方面论证项目可行性。"
            ),
        },
        {
            "id": "schedule",
            "title": "计划进度",
            "content": _build_schedule_template(period_months),
        },
        {
            "id": "budget",
            "title": "经费预算框架",
            "content": (
                f"1. 设备费\n"
                f"购置/试制仪器设备、现有设备升级等。\n\n"
                f"2. 材料费\n"
                f"原材料、试剂、药品等消耗品。\n\n"
                f"3. 测试化验加工费\n"
                f"检验、测试、化验、加工等费用。\n\n"
                f"4. 差旅费/会议费\n"
                f"国内/国际合作交流费用。\n\n"
                f"5. 出版/文献/知识产权费\n"
                f"论文发表、专利申请等费用。\n\n"
                f"6. 劳务费\n"
                f"研究生、博士后等人员劳务费。\n\n"
                f"7. 其他费用\n"
                f"根据{type_label}特点补充其他必要支出。"
            ),
        },
    ]


def _build_milestones(period_months: int) -> list[dict[str, str]]:
    """Build milestone template based on period."""
    if period_months <= 12:
        return [
            {"phase": "中期", "time": "第6月", "deliverable": "阶段性进展报告"},
            {"phase": "结题", "time": "第12月", "deliverable": "结题报告与成果"},
        ]
    elif period_months <= 24:
        return [
            {"phase": "年度检查", "time": "第12月", "deliverable": "年度进展报告"},
            {"phase": "中期", "time": "第12月", "deliverable": "中期检查报告"},
            {"phase": "结题", "time": "第24月", "deliverable": "结题报告与成果"},
        ]
    else:
        return [
            {"phase": "年度检查1", "time": "第12月", "deliverable": "第一年度进展报告"},
            {"phase": "中期", "time": "第18月", "deliverable": "中期检查报告"},
            {"phase": "年度检查2", "time": "第24月", "deliverable": "第二年度进展报告"},
            {"phase": "结题", "time": f"第{period_months}月", "deliverable": "结题报告与成果"},
        ]


def _build_risks() -> list[dict[str, str]]:
    """Build common risk template."""
    return [
        {
            "type": "技术风险",
            "description": "研究方法或技术路线可能存在不确定性",
            "mitigation": "准备备选方案，及时调整研究策略",
        },
        {
            "type": "进度风险",
            "description": "研究进度可能受外部因素影响",
            "mitigation": "合理安排时间节点，预留缓冲时间",
        },
        {
            "type": "资源风险",
            "description": "设备、人员或资金可能出现变动",
            "mitigation": "提前做好资源规划，建立应急机制",
        },
    ]


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


def _normalize_llm_sections(
    raw_sections: Any,
    template_sections: list[dict[str, str]],
) -> list[dict[str, str]] | None:
    """Normalize LLM-generated sections against template."""
    if not isinstance(raw_sections, list):
        return None

    normalized: list[dict[str, str]] = []
    for index, template_section in enumerate(template_sections):
        candidate = raw_sections[index] if index < len(raw_sections) else None
        if isinstance(candidate, dict):
            candidate_content = str(candidate.get("content") or "").strip()
            if candidate_content:
                normalized.append(
                    {
                        "id": template_section["id"],
                        "title": template_section["title"],
                        "content": candidate_content,
                        "source": "llm",
                    }
                )
                continue

        normalized.append(
            {
                "id": template_section["id"],
                "title": template_section["title"],
                "content": template_section["content"],
                "source": "template",
            }
        )

    # If LLM didn't provide meaningful content for any section, treat as invalid.
    if not any(section["source"] == "llm" for section in normalized):
        return None
    return normalized


PROPOSAL_OUTLINE_PROMPT = """请根据以下信息生成一份{type_label}申报书大纲，返回 JSON。

项目主题：{topic}
申报类型：{type_label}
项目周期：{period_months}个月
{memory_context}

你必须输出如下结构：
{{"sections":[{{"id":"section_id","title":"章节标题","content":"章节内容"}}]}}

章节必须包含以下内容（按顺序）：
{section_requirements}

要求：
1. 内容具体、可操作，避免空话套话
2. 符合学术写作规范
3. 根据项目周期合理规划进度
4. 预算框架要符合实际需求

仅返回 JSON。"""


async def _llm_generate_proposal_sections(
    *,
    topic: str,
    proposal_type: str,
    period_months: int,
    template_sections: list[dict[str, str]],
    preferred_model: str | None,
    memory_context: str | None,
) -> tuple[list[dict[str, str]] | None, str | None, str | None]:
    """Attempt to generate proposal sections using LLM. Returns (sections, model_id, error)."""
    from src.config import get_gen_models
    from src.models.factory import create_chat_model

    models = get_gen_models()
    if not models:
        return None, None, "no_generation_model_configured"

    model_id = preferred_model or models[0].id
    if not any(model.id == model_id for model in models):
        model_id = models[0].id

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        logger.exception("Failed to create model")
        return None, model_id, f"model_init_failed: {exc}"

    type_label = PROPOSAL_TYPES.get(proposal_type, "科研项目")
    section_requirements = "\n".join(
        f"- {section['id']}: {section['title']}" for section in template_sections
    )
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = PROPOSAL_OUTLINE_PROMPT.format(
        type_label=type_label,
        topic=topic,
        period_months=period_months,
        section_requirements=section_requirements,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.exception("LLM generation failed")
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_response(content)
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    sections = _normalize_llm_sections(parsed.get("sections"), template_sections)
    if sections is None:
        return None, model_id, "llm_sections_invalid"

    return sections, model_id, None


@register_feature_graph("proposal_outline", workspace_type="proposal")
async def proposal_outline_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute proposal outline generation with LLM-enhanced analysis.

    Pipeline: extract params -> normalize type -> LLM sections -> milestones/risks -> output
    Falls back to template mode if LLM unavailable.
    """
    params = payload.get("params", {})
    workspace_name = str(payload.get("workspace_name", ""))

    # Step 1: Extract and normalize parameters
    topic = str(params.get("topic") or workspace_name or "未命名项目").strip()
    proposal_type = _normalize_proposal_type(str(params.get("proposal_type", "other")))
    period_months = _normalize_period(params.get("period_months"), proposal_type)
    preferred_model = params.get("model_id")
    memory_context = initial_state.get("knowledge_context")

    # Step 2: Build template sections
    template_sections = _build_proposal_template_sections(
        topic=topic,
        proposal_type=proposal_type,
        period_months=period_months,
    )

    # Step 3: Try LLM generation
    llm_sections, model_id, generation_error = await _llm_generate_proposal_sections(
        topic=topic,
        proposal_type=proposal_type,
        period_months=period_months,
        template_sections=template_sections,
        preferred_model=preferred_model,
        memory_context=memory_context,
    )

    # Step 4: Build final output with fallback
    if llm_sections is not None:
        sections = llm_sections
        generation_mode = "llm"
    else:
        sections = [
            {
                "id": section["id"],
                "title": section["title"],
                "content": section["content"],
                "source": "template",
            }
            for section in template_sections
        ]
        generation_mode = "template_fallback"

    # Step 5: Build milestones and risks
    milestones = _build_milestones(period_months)
    risks = _build_risks()

    # Step 6: Return structured output
    type_label = PROPOSAL_TYPES.get(proposal_type, "科研项目")

    return {
        "schema_version": "v1",
        "output_language": PROPOSAL_OUTPUT_LANGUAGE,
        "topic": topic,
        "proposal_type": proposal_type,
        "proposal_type_label": type_label,
        "period_months": period_months,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "milestones": milestones,
        "risks": risks,
        "generated_at": _utc_now_iso(),
    }
