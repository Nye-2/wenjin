"""Service helpers for proposal workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. proposal outline generation (with template fallback),
2. background research payload assembly (with LLM-optional strategy).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from src.config import get_gen_models
from src.models.factory import create_chat_model

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


def _truncate(value: str, max_len: int = 280) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


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


def _normalize_period(period: int | str | None) -> int:
    """Normalize period to months."""
    if period is None:
        return 24
    try:
        return int(period)
    except (TypeError, ValueError):
        return 24


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
                "1. 研究意义\n"
                f"阐述\"{topic}\"的研究背景与理论/实践价值，"
                f"说明该研究对学科发展或行业应用的重要意义。\n\n"
                "2. 国内外研究现状及分析\n"
                "梳理国内外在相关领域的主要研究进展，"
                "分析现有研究的优势与不足，找出研究空白。\n\n"
                "3. 参考文献\n"
                "列出主要参考文献（建议10-20篇）。"
            ),
        },
        {
            "id": "objectives",
            "title": "研究目标与内容",
            "content": (
                "1. 研究目标\n"
                f"明确{type_label}的总体目标和具体目标，"
                "目标应具有可衡量性和可实现性。\n\n"
                "2. 研究内容\n"
                "分解为3-5个具体研究内容，"
                "每个内容应明确研究范围和预期成果。\n\n"
                "3. 拟解决的关键科学问题\n"
                "提炼1-3个关键科学问题或技术难题。"
            ),
        },
        {
            "id": "methodology",
            "title": "研究方案与技术路线",
            "content": (
                "1. 研究方法\n"
                "说明采用的主要研究方法（理论分析、实验研究、"
                "数值模拟、调查研究等）及其选择依据。\n\n"
                "2. 技术路线\n"
                "描述从问题提出到成果产出的完整技术路径，"
                "建议配合流程图说明。\n\n"
                "3. 可行性分析\n"
                "从理论、技术、资源等方面论证项目可行性。"
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
                "1. 设备费\n"
                "购置/试制仪器设备、现有设备升级等。\n\n"
                "2. 材料费\n"
                "原材料、试剂、药品等消耗品。\n\n"
                "3. 测试化验加工费\n"
                "检验、测试、化验、加工等费用。\n\n"
                "4. 差旅费/会议费\n"
                "国内/国际合作交流费用。\n\n"
                "5. 出版/文献/知识产权费\n"
                "论文发表、专利申请等费用。\n\n"
                "6. 劳务费\n"
                "研究生、博士后等人员劳务费。\n\n"
                "7. 其他费用\n"
                f"根据{type_label}特点补充其他必要支出。"
            ),
        },
    ]


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


def _extract_response_text(response: Any) -> str:
    """Extract text content from LLM response."""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return "\n".join(texts).strip()
    return str(content).strip()


def _parse_json_payload(raw_text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response with multiple extraction strategies."""
    if not raw_text:
        return None

    candidates = [raw_text.strip()]

    # Try to extract from code block
    code_block_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    # Try to extract from first brace to last brace
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
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


async def _try_generate_proposal_sections(
    *,
    topic: str,
    proposal_type: str,
    period_months: int,
    template_sections: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[list[dict[str, str]] | None, str | None, str | None]:
    """Attempt to generate proposal sections using LLM."""
    models = get_gen_models()
    if not models:
        return None, None, "no_generation_model_configured"

    model_id = preferred_model or models[0].id
    if not any(model.id == model_id for model in models):
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    type_label = PROPOSAL_TYPES.get(proposal_type, "科研项目")

    prompt = "\n".join(
        [
            f"请根据以下信息生成一份{type_label}申报书大纲，返回 JSON。",
            f"项目主题：{topic}",
            f"申报类型：{type_label}",
            f"项目周期：{period_months}个月",
            "你必须输出如下结构：",
            '{"sections":[{"id":"section_id","title":"章节标题","content":"章节内容"}]}',
            "章节必须包含以下内容（按顺序）：",
            "\n".join(f"- {section['id']}: {section['title']}" for section in template_sections),
            "要求：",
            "1. 内容具体、可操作，避免空话套话",
            "2. 符合学术写作规范",
            "3. 根据项目周期合理规划进度",
            "4. 预算框架要符合实际需求",
        ]
    )

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content="你是专业的科研项目申报书撰写助手，只输出 JSON 格式内容。"),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    sections = _normalize_llm_sections(parsed.get("sections"), template_sections)
    if sections is None:
        return None, model_id, "llm_sections_invalid"
    return sections, model_id, None


async def build_proposal_outline_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    topic: str,
    proposal_type: str,
    period_months: int | None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build proposal outline artifact content with template-first, LLM-optional strategy.

    Args:
        workspace_id: Workspace ID for context
        workspace_name: Workspace name for title generation
        topic: Project topic/theme
        proposal_type: Type of proposal (national_natural_science, provincial, etc.)
        period_months: Project duration in months
        preferred_model: Optional preferred LLM model ID

    Returns:
        Dict containing proposal outline content ready for artifact persistence
    """
    normalized_type = _normalize_proposal_type(proposal_type)
    normalized_topic = (topic or workspace_name or "未命名项目").strip()
    if not normalized_topic:
        normalized_topic = "未命名项目"

    normalized_period = _normalize_period(period_months)
    if normalized_period <= 0:
        normalized_period = DEFAULT_PERIODS.get(normalized_type, 24)

    template_sections = _build_proposal_template_sections(
        topic=normalized_topic,
        proposal_type=normalized_type,
        period_months=normalized_period,
    )

    llm_sections, model_id, generation_error = await _try_generate_proposal_sections(
        topic=normalized_topic,
        proposal_type=normalized_type,
        period_months=normalized_period,
        template_sections=template_sections,
        preferred_model=preferred_model,
    )

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

    milestones = _build_milestones(normalized_period)
    risks = _build_risks()

    type_label = PROPOSAL_TYPES.get(normalized_type, "科研项目")

    return {
        "schema_version": "v1",
        "output_language": PROPOSAL_OUTPUT_LANGUAGE,
        "topic": normalized_topic,
        "proposal_type": normalized_type,
        "proposal_type_label": type_label,
        "period_months": normalized_period,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "milestones": milestones,
        "risks": risks,
        "generated_at": _utc_now_iso(),
    }


# ============ Background Research Service ============


def _build_background_template_sections(
    *,
    keywords: str,
    industry_scope: str,
    time_range: str,
) -> list[dict[str, str]]:
    """Build template sections for background research."""
    return [
        {
            "id": "overview",
            "title": "现状综述",
            "content": (
                f"围绕\"{keywords}\"进行背景调研：\n\n"
                "1. 概念定义与内涵\n"
                "明确核心概念的定义、内涵与外延。\n\n"
                "2. 发展历程\n"
                "梳理该领域的发展脉络和重要里程碑。\n\n"
                "3. 当前研究热点\n"
                f"分析{industry_scope}领域当前的研究热点与趋势。\n\n"
                "4. 主要研究力量\n"
                "介绍国内外主要研究机构、团队及其代表性工作。"
            ),
        },
        {
            "id": "problems",
            "title": "问题清单",
            "content": (
                f"基于{time_range}内的研究现状，梳理存在的主要问题：\n\n"
                "1. 理论层面问题\n"
                "- 现有理论框架的局限性\n"
                "- 关键理论问题尚未解决\n\n"
                "2. 技术层面问题\n"
                "- 技术实现的主要瓶颈\n"
                "- 工程化应用的难点\n\n"
                "3. 应用层面问题\n"
                "- 实际应用中的挑战\n"
                "- 推广普及的障碍"
            ),
        },
        {
            "id": "directions",
            "title": "可行技术方向",
            "content": (
                f"针对\"{keywords}\"，提出以下可行的研究方向：\n\n"
                "方向一：理论创新\n"
                "- 研究内容：\n"
                "- 预期突破：\n"
                "- 可行性评估：\n\n"
                "方向二：方法改进\n"
                "- 研究内容：\n"
                "- 预期突破：\n"
                "- 可行性评估：\n\n"
                "方向三：应用拓展\n"
                "- 研究内容：\n"
                "- 预期突破：\n"
                "- 可行性评估："
            ),
        },
    ]


def _build_references_template(keywords: str) -> list[dict[str, str]]:
    """Build placeholder references structure."""
    return [
        {
            "title": "参考文献1（待补充）",
            "authors": "",
            "year": "",
            "venue": "",
            "note": f"与{keywords}相关的核心文献",
        },
        {
            "title": "参考文献2（待补充）",
            "authors": "",
            "year": "",
            "venue": "",
            "note": "综述性文献",
        },
        {
            "title": "参考文献3（待补充）",
            "authors": "",
            "year": "",
            "venue": "",
            "note": "最新研究进展",
        },
    ]


async def _try_generate_background_sections(
    *,
    keywords: str,
    industry_scope: str,
    time_range: str,
    template_sections: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[list[dict[str, str]] | None, list[dict[str, str]] | None, str | None, str | None]:
    """Attempt to generate background research sections using LLM."""
    models = get_gen_models()
    if not models:
        return None, None, None, "no_generation_model_configured"

    model_id = preferred_model or models[0].id
    if not any(model.id == model_id for model in models):
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, None, model_id, f"model_init_failed: {exc}"

    prompt = "\n".join(
        [
            "请根据以下信息生成项目背景调研报告，返回 JSON。",
            f"主题关键词：{keywords}",
            f"行业范围：{industry_scope}",
            f"时间范围：{time_range}",
            "你必须输出如下结构：",
            "{",
            '  "sections":[{"id":"section_id","title":"章节标题","content":"章节内容"}],',
            '  "references":[{"title":"标题","authors":"作者","year":"年份","venue":"期刊/会议"}]',
            "}",
            "章节必须包含以下内容（按顺序）：",
            "\n".join(f"- {section['id']}: {section['title']}" for section in template_sections),
            "要求：",
            "1. 内容具体、有针对性",
            "2. 问题清单要列出具体问题而非泛泛而谈",
            "3. 技术方向要具有可行性和创新性",
            "4. 参考文献要列出5-10条真实或合理的文献",
        ]
    )

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content="你是专业的科研背景调研助手，只输出 JSON 格式内容。"),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        return None, None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, None, model_id, "llm_output_not_json"

    sections = _normalize_llm_sections(parsed.get("sections"), template_sections)
    if sections is None:
        return None, None, model_id, "llm_sections_invalid"

    # Extract references if provided
    raw_refs = parsed.get("references")
    references = None
    if isinstance(raw_refs, list) and raw_refs:
        references = []
        for ref in raw_refs[:10]:
            if isinstance(ref, dict):
                references.append(
                    {
                        "title": str(ref.get("title") or ""),
                        "authors": str(ref.get("authors") or ""),
                        "year": str(ref.get("year") or ""),
                        "venue": str(ref.get("venue") or ""),
                    }
                )
        if not references:
            references = None

    return sections, references, model_id, None


async def build_background_research_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    keywords: str,
    industry_scope: str,
    time_range: str,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build background research artifact content with template-first, LLM-optional strategy.

    Args:
        workspace_id: Workspace ID for context
        workspace_name: Workspace name for title generation
        keywords: Research topic keywords
        industry_scope: Industry/domain scope for the research
        time_range: Time range for literature review (e.g., "近5年", "2020-2024")
        preferred_model: Optional preferred LLM model ID

    Returns:
        Dict containing background research content ready for artifact persistence
    """
    normalized_keywords = (keywords or workspace_name or "未指定主题").strip()
    if not normalized_keywords:
        normalized_keywords = "未指定主题"

    normalized_industry = (industry_scope or "相关领域").strip()
    if not normalized_industry:
        normalized_industry = "相关领域"

    normalized_time = (time_range or "近5年").strip()
    if not normalized_time:
        normalized_time = "近5年"

    template_sections = _build_background_template_sections(
        keywords=normalized_keywords,
        industry_scope=normalized_industry,
        time_range=normalized_time,
    )

    llm_sections, llm_refs, model_id, generation_error = await _try_generate_background_sections(
        keywords=normalized_keywords,
        industry_scope=normalized_industry,
        time_range=normalized_time,
        template_sections=template_sections,
        preferred_model=preferred_model,
    )

    if llm_sections is not None:
        sections = llm_sections
        generation_mode = "llm"
        references = llm_refs or _build_references_template(normalized_keywords)
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
        references = _build_references_template(normalized_keywords)

    return {
        "schema_version": "v1",
        "output_language": PROPOSAL_OUTPUT_LANGUAGE,
        "keywords": normalized_keywords,
        "industry_scope": normalized_industry,
        "time_range": normalized_time,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "references": references,
        "generated_at": _utc_now_iso(),
    }
