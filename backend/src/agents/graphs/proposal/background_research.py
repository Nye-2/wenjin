"""Background Research sub-graph — LLM-powered background research generation.

This module implements the background_research feature using LangGraph pattern:
- Parameter extraction and normalization
- LLM-powered section generation with template fallback
- Reference generation
- Structured output with generation_mode tracking
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)

BACKGROUND_OUTPUT_LANGUAGE = "zh"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
                f"1. 概念定义与内涵\n"
                f"明确核心概念的定义、内涵与外延。\n\n"
                f"2. 发展历程\n"
                f"梳理该领域的发展脉络和重要里程碑。\n\n"
                f"3. 当前研究热点\n"
                f"分析{industry_scope}领域当前的研究热点与趋势。\n\n"
                f"4. 主要研究力量\n"
                f"介绍国内外主要研究机构、团队及其代表性工作。"
            ),
        },
        {
            "id": "problems",
            "title": "问题清单",
            "content": (
                f"基于{time_range}内的研究现状，梳理存在的主要问题：\n\n"
                f"1. 理论层面问题\n"
                f"- 现有理论框架的局限性\n"
                f"- 关键理论问题尚未解决\n\n"
                f"2. 技术层面问题\n"
                f"- 技术实现的主要瓶颈\n"
                f"- 工程化应用的难点\n\n"
                f"3. 应用层面问题\n"
                f"- 实际应用中的挑战\n"
                f"- 推广普及的障碍"
            ),
        },
        {
            "id": "directions",
            "title": "可行技术方向",
            "content": (
                f"针对\"{keywords}\"，提出以下可行的研究方向：\n\n"
                f"方向一：理论创新\n"
                f"- 研究内容：\n"
                f"- 预期突破：\n"
                f"- 可行性评估：\n\n"
                f"方向二：方法改进\n"
                f"- 研究内容：\n"
                f"- 预期突破：\n"
                f"- 可行性评估：\n\n"
                f"方向三：应用拓展\n"
                f"- 研究内容：\n"
                f"- 预期突破：\n"
                f"- 可行性评估："
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


def _normalize_references(raw_refs: Any, keywords: str) -> list[dict[str, str]] | None:
    """Normalize LLM-generated references."""
    if not isinstance(raw_refs, list) or not raw_refs:
        return None

    references: list[dict[str, str]] = []
    for ref in raw_refs[:10]:
        if isinstance(ref, dict):
            title = str(ref.get("title") or "").strip()
            if title:
                references.append(
                    {
                        "title": title,
                        "authors": str(ref.get("authors") or ""),
                        "year": str(ref.get("year") or ""),
                        "venue": str(ref.get("venue") or ""),
                    }
                )

    return references if references else None


BACKGROUND_RESEARCH_PROMPT = """请根据以下信息生成项目背景调研报告，返回 JSON。

主题关键词：{keywords}
行业范围：{industry_scope}
时间范围：{time_range}
{memory_context}

你必须输出如下结构：
{{
  "sections":[{{"id":"section_id","title":"章节标题","content":"章节内容"}}],
  "references":[{{"title":"标题","authors":"作者","year":"年份","venue":"期刊/会议"}}]
}}

章节必须包含以下内容（按顺序）：
{section_requirements}

要求：
1. 内容具体、有针对性
2. 问题清单要列出具体问题而非泛泛而谈
3. 技术方向要具有可行性和创新性
4. 参考文献要列出5-10条真实或合理的文献

仅返回 JSON。"""


async def _llm_generate_background_sections(
    *,
    keywords: str,
    industry_scope: str,
    time_range: str,
    template_sections: list[dict[str, str]],
    preferred_model: str | None,
    memory_context: str | None,
) -> tuple[list[dict[str, str]] | None, list[dict[str, str]] | None, str | None, str | None]:
    """Attempt to generate background research sections using LLM.

    Returns (sections, references, model_id, error).
    """
    from src.config import get_gen_models
    from src.models.factory import create_chat_model

    models = get_gen_models()
    if not models:
        return None, None, None, "no_generation_model_configured"

    model_id = preferred_model or models[0].id
    if not any(model.id == model_id for model in models):
        model_id = models[0].id

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        logger.exception("Failed to create model")
        return None, None, model_id, f"model_init_failed: {exc}"

    section_requirements = "\n".join(
        f"- {section['id']}: {section['title']}" for section in template_sections
    )
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = BACKGROUND_RESEARCH_PROMPT.format(
        keywords=keywords,
        industry_scope=industry_scope,
        time_range=time_range,
        section_requirements=section_requirements,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.exception("LLM generation failed")
        return None, None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_response(content)
    if parsed is None:
        return None, None, model_id, "llm_output_not_json"

    sections = _normalize_llm_sections(parsed.get("sections"), template_sections)
    if sections is None:
        return None, None, model_id, "llm_sections_invalid"

    # Extract references if provided
    references = _normalize_references(parsed.get("references"), keywords)

    return sections, references, model_id, None


@register_feature_graph("background_research", workspace_type="proposal")
async def background_research_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute background research generation with LLM-enhanced analysis.

    Pipeline: extract params -> normalize scope -> LLM sections -> references -> output
    Falls back to template mode if LLM unavailable.
    """
    params = payload.get("params", {})
    workspace_name = str(payload.get("workspace_name", ""))

    # Step 1: Extract and normalize parameters
    keywords = str(params.get("keywords") or workspace_name or "未指定主题").strip()
    industry_scope = str(params.get("industry_scope") or "相关领域").strip()
    time_range = str(params.get("time_range") or "近5年").strip()
    preferred_model = params.get("model_id")
    memory_context = initial_state.get("knowledge_context")

    # Step 2: Build template sections
    template_sections = _build_background_template_sections(
        keywords=keywords,
        industry_scope=industry_scope,
        time_range=time_range,
    )

    # Step 3: Try LLM generation
    llm_sections, llm_refs, model_id, generation_error = await _llm_generate_background_sections(
        keywords=keywords,
        industry_scope=industry_scope,
        time_range=time_range,
        template_sections=template_sections,
        preferred_model=preferred_model,
        memory_context=memory_context,
    )

    # Step 4: Build final output with fallback
    if llm_sections is not None:
        sections = llm_sections
        generation_mode = "llm"
        references = llm_refs or _build_references_template(keywords)
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
        references = _build_references_template(keywords)

    # Step 5: Return structured output
    return {
        "schema_version": "v1",
        "output_language": BACKGROUND_OUTPUT_LANGUAGE,
        "keywords": keywords,
        "industry_scope": industry_scope,
        "time_range": time_range,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "references": references,
        "generated_at": _utc_now_iso(),
    }
