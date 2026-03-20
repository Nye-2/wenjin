"""Service helpers for SCI workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. literature search (with local data or template fallback),
2. paper analysis (structured method/experiment/conclusion extraction).
3. SCI section writing (context-aware draft generation with fallback).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts import ArtifactType
from src.database import get_db_session
from src.models.factory import create_chat_model
from src.models.router import list_user_selectable_models, route_writing_model
from src.services.literature_service import LiteratureService
from src.task.progress import emit_runtime_update, get_runtime_state
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    runtime_progress_for_phase,
    set_runtime_phase,
    upsert_runtime_block,
)

logger = logging.getLogger(__name__)

SCI_SCHEMA_VERSION = "v1"
SCI_OUTPUT_LANGUAGE = "en"


async def _emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    """Emit the currently bound runtime state if available."""
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


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _truncate(value: str, max_len: int = 280) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


def _normalize_discipline(discipline: str | None) -> str:
    """Normalize workspace discipline for search context."""
    if not discipline:
        return "综合"
    discipline_map = {
        "computer_science": "计算机科学",
        "cs": "计算机科学",
        "engineering": "工程学",
        "physics": "物理学",
        "chemistry": "化学",
        "biology": "生物学",
        "medicine": "医学",
        "economics": "经济学",
        "management": "管理学",
        "social_science": "社会科学",
    }
    normalized = (discipline or "").strip().lower().replace(" ", "_")
    return discipline_map.get(normalized, discipline)


SCI_WRITING_SECTION_MAP: dict[str, str] = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related_work": "Related Work",
    "methodology": "Methodology",
    "experiments": "Experiments",
    "results": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}


async def _load_workspace_literature(workspace_id: str) -> list[dict[str, Any]]:
    """Load literature from workspace for context enrichment."""
    try:
        async with get_db_session() as db:
            service = LiteratureService(db)
            response = await service.list_literature(workspace_id, offset=0, limit=100)
    except Exception as exc:
        logger.warning(
            "Failed to load workspace literature for '%s', fallback to empty context: %s",
            workspace_id,
            exc,
        )
        return []

    items = response.get("items")
    return items if isinstance(items, list) else []


def _build_literature_search_template(
    query: str,
    discipline: str,
) -> dict[str, Any]:
    """Build a template-based literature search result when LLM is unavailable."""
    return {
        "query": query,
        "discipline": discipline,
        "papers": [],
        "top_hits": [],
        "filters": {
            "year_range": {"min": 2020, "max": 2025},
            "sources": ["Semantic Scholar", "CrossRef", "Google Scholar"],
            "quartiles": ["Q1", "Q2", "Q3", "Q4"],
        },
        "summary": f"针对“{query}”的文献检索。请配置外部检索服务以获取实时结果。",
        "search_strategy": "template_fallback",
        "generated_at": _utc_now_iso(),
    }


async def _try_llm_literature_search(
    *,
    query: str,
    discipline: str,
    existing_literature: list[dict[str, Any]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based literature search synthesis."""
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    # Build context from existing literature
    literature_context = ""
    if existing_literature:
        lit_summaries = []
        for lit in existing_literature[:10]:
            title = lit.get("title", "未知标题")
            year = lit.get("year", "")
            venue = lit.get("venue", "")
            lit_summaries.append(f"- {title} ({year}) - {venue}")
        literature_context = "已有相关文献：\n" + "\n".join(lit_summaries)

    prompt = "\n".join([
        "请根据检索需求生成文献检索建议和分析，返回 JSON。",
        f"检索查询：{query}",
        f"学科领域：{discipline}",
        literature_context if literature_context else "暂无已有文献",
        "",
        "你必须输出如下 JSON 结构：",
        '{"papers":[{"title":"论文标题","authors":["作者1"],"year":2024,"venue":"期刊/会议","abstract":"摘要","relevance":"相关性说明"}],"top_hits":[{"title":"高相关论文","reason":"推荐理由"}],"filters":{"year_range":{"min":2020,"max":2025},"sources":["数据源"],"quartiles":["Q1","Q2"]},"summary":"检索结果综述"}',
        "",
        "要求：",
        "1. papers 数组提供 5-10 篇推荐文献（基于已有文献或领域常识）",
        "2. top_hits 提供 3 篇最相关的论文推荐",
        "3. filters 提供合理的筛选维度建议",
        "4. summary 提供检索结果综述和研究方向建议",
        "5. 内容需与学科领域相关，具备学术价值",
    ])

    try:
        response = await model.ainvoke([
            SystemMessage(content="你是学术文献检索专家，输出 JSON 格式的检索结果。"),
            HumanMessage(content=prompt),
        ])
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    raw_text = _extract_response_text(response)
    parsed = _parse_json_payload(raw_text)
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    return {
        "query": query,
        "discipline": discipline,
        "papers": parsed.get("papers", [])[:10],
        "top_hits": parsed.get("top_hits", [])[:5],
        "filters": parsed.get("filters", {
            "year_range": {"min": 2020, "max": 2025},
            "sources": ["Semantic Scholar", "CrossRef"],
            "quartiles": ["Q1", "Q2"],
        }),
        "summary": parsed.get("summary", ""),
        "search_strategy": "llm_synthesis",
        "generated_at": _utc_now_iso(),
    }, model_id, None


def _extract_response_text(response: Any) -> str:
    """Extract text from LLM response."""
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

    code_block_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

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


async def build_literature_search_payload(
    *,
    workspace_id: str,
    query: str,
    discipline: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build literature search artifact content with LLM synthesis + fallback.

    Args:
        workspace_id: UUID of the workspace
        query: Search query string
        discipline: Academic discipline for context
        preferred_model: Optional model ID for generation

    Returns:
        Structured literature search result payload
    """
    normalized_query = (query or "").strip()
    if not normalized_query:
        normalized_query = "研究主题"

    normalized_discipline = _normalize_discipline(discipline)
    runtime = get_runtime_state()

    # Load existing literature for context
    existing_literature = await _load_workspace_literature(workspace_id)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "context",
                "kind": "metrics",
                "title": "检索上下文",
                "entries": [
                    {"label": "历史文献", "value": str(len(existing_literature))},
                    {"label": "学科", "value": normalized_discipline},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="检索上下文已就绪",
            description=f"已加载 {len(existing_literature)} 条历史文献作为检索参考。",
            tone="info",
        )
        advance_runtime_phase(runtime, "prepare", "retrieve")
        await _emit_bound_runtime(
            message="正在生成候选论文与高相关命中...",
            current_phase="retrieve",
            stage_transition=True,
        )

    # Try LLM-based synthesis
    llm_result, model_id, generation_error = await _try_llm_literature_search(
        query=normalized_query,
        discipline=normalized_discipline,
        existing_literature=existing_literature,
        preferred_model=preferred_model,
    )

    if llm_result is not None:
        llm_result["model_id"] = model_id
        llm_result["existing_literature_count"] = len(existing_literature)
        if runtime is not None:
            top_hits = llm_result.get("top_hits")
            upsert_runtime_block(
                runtime,
                {
                    "id": "search-results",
                    "kind": "list",
                    "title": "高相关命中",
                    "description": "模型已整理候选文献与优先命中",
                    "items": [
                        {
                            "title": str(item.get("title") or "Untitled"),
                            "description": str(item.get("summary") or ""),
                            "meta": str(item.get("venue") or ""),
                            "badge": str(item.get("year") or "") or None,
                        }
                        for item in (top_hits or [])[:6]
                        if isinstance(item, dict)
                    ],
                },
            )
            upsert_runtime_block(
                runtime,
                {
                    "id": "result-summary",
                    "kind": "metrics",
                    "title": "检索结果",
                    "entries": [
                        {"label": "候选文献", "value": str(len(llm_result.get("papers") or []))},
                        {"label": "Top Hits", "value": str(len(top_hits) if isinstance(top_hits, list) else 0)},
                        {"label": "生成模式", "value": str(llm_result.get("search_strategy") or "llm")},
                    ],
                },
            )
            append_runtime_activity(
                runtime,
                title="检索完成",
                description="已生成候选文献和高相关命中列表。",
                tone="success",
            )
            advance_runtime_phase(runtime, "retrieve", "finalize")
            await _emit_bound_runtime(
                message="正在整理文献检索产物...",
                current_phase="finalize",
                stage_transition=True,
            )
        return llm_result

    # Fallback to template
    template_result = _build_literature_search_template(
        query=normalized_query,
        discipline=normalized_discipline,
    )
    template_result["model_id"] = model_id
    template_result["generation_error"] = generation_error
    template_result["existing_literature_count"] = len(existing_literature)
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "result-summary",
                "kind": "metrics",
                "title": "检索结果",
                "entries": [
                    {"label": "候选文献", "value": "0"},
                    {"label": "Top Hits", "value": "0"},
                    {"label": "生成模式", "value": "template_fallback"},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="检索退回模板",
            description="当前模型未返回结构化结果，已生成模板化检索输出。",
            tone="warning",
        )
        advance_runtime_phase(runtime, "retrieve", "finalize")
        await _emit_bound_runtime(
            message="正在整理模板化检索结果...",
            current_phase="finalize",
            stage_transition=True,
        )
    return template_result


def _build_paper_analysis_template(
    paper_title: str,
    paper_id: str | None = None,
) -> dict[str, Any]:
    """Build template-based paper analysis when LLM is unavailable."""
    return {
        "paper_id": paper_id,
        "paper_title": paper_title,
        "analysis_mode": "template_fallback",
        "sections": {
            "methodology": {
                "title": "研究方法",
                "content": "请配置 LLM 服务以获取深度方法分析。",
                "key_points": ["研究设计", "数据收集", "分析方法"],
            },
            "experiments": {
                "title": "实验设计",
                "content": "请配置 LLM 服务以获取实验设计分析。",
                "key_points": ["实验设置", "基准对比", "评价指标"],
            },
            "conclusions": {
                "title": "研究结论",
                "content": "请配置 LLM 服务以获取结论摘要。",
                "key_points": ["主要发现", "研究贡献", "局限性"],
            },
            "innovations": {
                "title": "创新点",
                "content": "请配置 LLM 服务以获取创新点分析。",
                "key_points": ["方法创新", "理论贡献", "应用价值"],
            },
        },
        "summary": f"《{paper_title}》的结构化分析。请配置 LLM 服务以获取深度分析。",
        "generated_at": _utc_now_iso(),
    }


async def _try_llm_paper_analysis(
    *,
    paper_title: str,
    paper_abstract: str | None = None,
    paper_content: str | None = None,
    preferred_model: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based paper analysis."""
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    # Build context from paper info
    context_parts = [f"论文标题：{paper_title}"]
    if paper_abstract:
        context_parts.append(f"摘要：{paper_abstract}")
    if paper_content:
        context_parts.append(f"内容片段：{_truncate(paper_content, max_len=2000)}")

    prompt = "\n".join([
        "请对以下论文进行结构化分析，返回 JSON。",
        "",
        *context_parts,
        "",
        "你必须输出如下 JSON 结构：",
        '{"sections":{"methodology":{"title":"研究方法","content":"方法描述","key_points":["要点1","要点2"]},"experiments":{"title":"实验设计","content":"实验描述","key_points":["要点1"]},"conclusions":{"title":"研究结论","content":"结论描述","key_points":["要点1"]},"innovations":{"title":"创新点","content":"创新描述","key_points":["要点1"]}},"summary":"论文整体评价","quality_assessment":{"methodology_rigor":"高/中/低","experiment_completeness":"高/中/低","contribution_level":"高/中/低"},"recommendations":["后续研究建议1","建议2"]}',
        "",
        "要求：",
        "1. methodology 分析研究方法、技术路线和数据来源",
        "2. experiments 分析实验设计、基准和评价指标",
        "3. conclusions 总结主要发现和研究贡献",
        "4. innovations 提炼核心创新点和理论贡献",
        "5. summary 提供 100-200 字的整体评价",
        "6. 内容需客观准确，具备学术参考价值",
    ])

    try:
        response = await model.ainvoke([
            SystemMessage(content="你是学术论文分析专家，输出 JSON 格式的结构化分析。"),
            HumanMessage(content=prompt),
        ])
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    raw_text = _extract_response_text(response)
    parsed = _parse_json_payload(raw_text)
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    # Normalize sections
    sections = parsed.get("sections", {})
    default_sections = {
        "methodology": {
            "title": "研究方法",
            "content": "分析方法暂缺",
            "key_points": [],
        },
        "experiments": {
            "title": "实验设计",
            "content": "实验分析暂缺",
            "key_points": [],
        },
        "conclusions": {
            "title": "研究结论",
            "content": "结论分析暂缺",
            "key_points": [],
        },
        "innovations": {
            "title": "创新点",
            "content": "创新点分析暂缺",
            "key_points": [],
        },
    }

    normalized_sections = {}
    for key, default in default_sections.items():
        if key in sections and isinstance(sections[key], dict):
            normalized_sections[key] = {
                "title": sections[key].get("title", default["title"]),
                "content": sections[key].get("content", default["content"]),
                "key_points": sections[key].get("key_points", []),
            }
        else:
            normalized_sections[key] = default

    return {
        "paper_title": paper_title,
        "analysis_mode": "llm",
        "sections": normalized_sections,
        "summary": parsed.get("summary", ""),
        "quality_assessment": parsed.get("quality_assessment", {}),
        "recommendations": parsed.get("recommendations", [])[:5],
        "generated_at": _utc_now_iso(),
    }, model_id, None


async def build_paper_analysis_payload(
    *,
    workspace_id: str,
    paper_id: str | None = None,
    paper_title: str | None = None,
    paper_abstract: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build paper analysis artifact content with LLM analysis + fallback.

    Args:
        workspace_id: UUID of the workspace
        paper_id: Optional paper ID for reference
        paper_title: Paper title (required if paper_id not provided)
        paper_abstract: Optional paper abstract for context
        preferred_model: Optional model ID for generation

    Returns:
        Structured paper analysis result payload
    """
    # Resolve paper title
    resolved_title = paper_title
    if not resolved_title:
        resolved_title = "未命名论文"
    runtime = get_runtime_state()

    # Try to load more paper context if paper_id is provided
    paper_content = None
    if paper_id:
        try:
            from src.academic.services.paper_service import PaperService
            async with get_db_session() as db:
                service = PaperService(db)
                paper = await service.get(paper_id)
                if paper:
                    resolved_title = paper.title or resolved_title
                    paper_abstract = paper.abstract or paper_abstract
        except Exception as e:
            logger.warning(f"Failed to load paper {paper_id}: {e}")

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "paper-context",
                "kind": "metrics",
                "title": "论文上下文",
                "entries": [
                    {"label": "标题", "value": resolved_title},
                    {"label": "Paper ID", "value": paper_id or "未提供"},
                    {"label": "摘要", "value": "已提供" if paper_abstract else "未提供"},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="论文上下文已就绪",
            description="已解析论文标题和摘要，准备开始结构化分析。",
            tone="info",
        )
        advance_runtime_phase(runtime, "prepare", "analyze")
        await _emit_bound_runtime(
            message="正在提炼方法、实验和创新点...",
            current_phase="analyze",
            stage_transition=True,
        )

    # Try LLM-based analysis
    llm_result, model_id, generation_error = await _try_llm_paper_analysis(
        paper_title=resolved_title,
        paper_abstract=paper_abstract,
        paper_content=paper_content,
        preferred_model=preferred_model,
    )

    if llm_result is not None:
        llm_result["paper_id"] = paper_id
        llm_result["model_id"] = model_id
        if runtime is not None:
            sections = llm_result.get("sections")
            recommendations = llm_result.get("recommendations")
            upsert_runtime_block(
                runtime,
                {
                    "id": "analysis-sections",
                    "kind": "list",
                    "title": "分析分区",
                    "description": "核心分析章节与摘要",
                    "items": [
                        {
                            "title": str(section.get("title") or key),
                            "description": str(section.get("content") or "")[:220],
                            "meta": (
                                f"{len(section.get('key_points', []))} 个要点"
                                if isinstance(section.get("key_points"), list)
                                else ""
                            ),
                        }
                        for key, section in (sections or {}).items()
                        if isinstance(section, dict)
                    ],
                },
            )
            if isinstance(recommendations, list):
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "recommendations",
                        "kind": "list",
                        "title": "后续建议",
                        "items": [
                            {"title": str(item), "description": ""}
                            for item in recommendations[:5]
                        ],
                    },
                )
            append_runtime_activity(
                runtime,
                title="结构化分析完成",
                description="已输出方法、实验、结论和创新点分析。",
                tone="success",
            )
            advance_runtime_phase(runtime, "analyze", "finalize")
            await _emit_bound_runtime(
                message="正在整理论文分析产物...",
                current_phase="finalize",
                stage_transition=True,
            )
        return llm_result

    # Fallback to template
    template_result = _build_paper_analysis_template(
        paper_title=resolved_title,
        paper_id=paper_id,
    )
    template_result["model_id"] = model_id
    template_result["generation_error"] = generation_error
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "analysis-sections",
                "kind": "list",
                "title": "分析分区",
                "description": "模板化分区结构",
                "items": [
                    {
                        "title": str(section.get("title") or key),
                        "description": str(section.get("content") or "")[:180],
                        "meta": "template",
                    }
                    for key, section in (template_result.get("sections") or {}).items()
                    if isinstance(section, dict)
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="分析退回模板",
            description="当前模型未返回结构化分析，已生成模板化输出。",
            tone="warning",
        )
        advance_runtime_phase(runtime, "analyze", "finalize")
        await _emit_bound_runtime(
            message="正在整理模板化分析结果...",
            current_phase="finalize",
            stage_transition=True,
        )
    return template_result


def _normalize_section_type(section_type: str | None) -> str:
    if not section_type:
        return "introduction"
    normalized = section_type.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in SCI_WRITING_SECTION_MAP else "introduction"


def _resolve_section_title(section_type: str) -> str:
    return SCI_WRITING_SECTION_MAP.get(section_type, "Section")


def _estimate_word_count(content: str) -> int:
    """Estimate mixed Chinese/English word count for draft metadata."""
    text = content.strip()
    if not text:
        return 0
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    return zh_chars + en_words


async def _load_artifact_context_summaries(
    *,
    workspace_id: str,
    context_artifact_ids: list[str],
) -> list[dict[str, str]]:
    """Load and summarize context artifacts for SCI writing."""
    summaries: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    preferred_types = {
        ArtifactType.PAPER_ANALYSIS.value,
        ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        ArtifactType.PAPER_DRAFT.value,
    }

    async with get_db_session() as db:
        service = ArtifactService(db)

        for artifact_id in context_artifact_ids:
            artifact = await service.get(artifact_id)
            if not artifact or str(artifact.workspace_id) != workspace_id:
                continue
            artifact_id_str = str(artifact.id)
            if artifact_id_str in seen_ids:
                continue
            seen_ids.add(artifact_id_str)
            summary = _summarize_artifact_for_prompt(artifact.type, _safe_dict(artifact.content))
            summaries.append(
                {
                    "id": artifact_id_str,
                    "type": artifact.type,
                    "title": artifact.title or artifact.type,
                    "summary": summary,
                }
            )

        if len(summaries) < 5:
            recent_artifacts = await service.list_by_workspace(
                workspace_id=workspace_id,
                limit=20,
                offset=0,
            )
            for artifact in recent_artifacts:
                if len(summaries) >= 5:
                    break
                artifact_id_str = str(artifact.id)
                if artifact_id_str in seen_ids:
                    continue
                if artifact.type not in preferred_types:
                    continue
                seen_ids.add(artifact_id_str)
                summary = _summarize_artifact_for_prompt(
                    artifact.type,
                    _safe_dict(artifact.content),
                )
                summaries.append(
                    {
                        "id": artifact_id_str,
                        "type": artifact.type,
                        "title": artifact.title or artifact.type,
                        "summary": summary,
                    }
                )

    return summaries


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summarize_artifact_for_prompt(artifact_type: str, content: dict[str, Any]) -> str:
    if artifact_type == ArtifactType.PAPER_ANALYSIS.value:
        summary = str(content.get("summary") or "").strip()
        return _truncate(summary, 320) if summary else "论文分析结果"
    if artifact_type == ArtifactType.LITERATURE_SEARCH_RESULTS.value:
        query = str(content.get("query") or "").strip()
        top_hits = content.get("top_hits")
        hit_count = len(top_hits) if isinstance(top_hits, list) else 0
        return f"文献检索主题：{query or '未命名主题'}；高相关命中 {hit_count} 篇。"
    if artifact_type == ArtifactType.PAPER_DRAFT.value:
        section_title = str(content.get("section_title") or content.get("section_type") or "章节").strip()
        draft_excerpt = str(content.get("content") or "").strip()
        if draft_excerpt:
            return f"{section_title}草稿：{_truncate(draft_excerpt, 240)}"
        return f"{section_title}草稿"
    return "参考产出内容"


def _build_sci_writing_template(
    *,
    paper_title: str,
    section_type: str,
    target_words: int,
) -> dict[str, Any]:
    section_title = _resolve_section_title(section_type)
    section_focus = {
        "abstract": "research objective, method, key results, and conclusion",
        "introduction": "background, problem statement, and contributions",
        "related_work": "comparison with prior work and identified research gap",
        "methodology": "method framework, core approach, and design motivation",
        "experiments": "experimental setup, metrics, and baselines",
        "results": "primary findings, error analysis, and interpretability",
        "discussion": "limitations, applicability boundary, and improvement directions",
        "conclusion": "summary and future work",
    }.get(section_type, "core claims and evidence structure for this section")

    content = (
        f"{section_title} Draft Template\n"
        f"The paper \"{paper_title}\" should focus this section on {section_focus}.\n\n"
        "Paragraph 1: explain the role of this section in the full paper and align it with the research objective.\n"
        "Paragraph 2: provide the core reasoning chain, supported by method, experiment, or result evidence.\n"
        "Paragraph 3: summarize limitations or next steps and prepare transition to subsequent sections.\n\n"
        f"Suggested length: around {target_words} words. Refine with real data, equations, and figures."
    )
    outline = [
        f"{section_title} objective and boundary",
        "core claims and evidence organization",
        "section summary and transition",
    ]
    references = [
        "Add core references directly supporting the section claims",
        "Attach reproducible experiment or data evidence for key conclusions",
    ]
    return {
        "section_title": section_title,
        "content": content,
        "outline": outline,
        "references": references,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "writing_mode": "template_fallback",
    }


async def _try_llm_sci_writing(
    *,
    paper_title: str,
    section_type: str,
    target_words: int,
    context_summaries: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based SCI section writing."""
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.4)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    section_title = _resolve_section_title(section_type)
    context_lines = []
    for item in context_summaries[:5]:
        context_lines.append(
            f"- [{item.get('type', 'artifact')}] {item.get('title', 'Untitled')}: {item.get('summary', '')}"
        )
    context_block = "\n".join(context_lines) if context_lines else "- No usable context artifacts."

    prompt = "\n".join(
        [
            "Write a SCI paper section draft in English and return JSON only.",
            f"Paper title: {paper_title}",
            f"Section type: {section_type}",
            f"Section title: {section_title}",
            f"Target length: around {target_words} words",
            "",
            "Available context summaries:",
            context_block,
            "",
            "Required JSON schema:",
            '{"section_title":"Section Title","content":"Section body in English","outline":["Subsection 1","Subsection 2"],"references":["Reference suggestion 1","Reference suggestion 2"]}',
            "",
            "Constraints:",
            "1. content must be directly editable academic prose in English.",
            "2. Keep a rigorous and specific academic tone.",
            "3. If context lacks evidence, provide supplemental suggestions in references.",
            "4. Do not output markdown code blocks or extra explanatory text.",
        ]
    )

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content="You are a SCI writing assistant. Output JSON only, in English."),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    content = str(parsed.get("content") or "").strip()
    if not content:
        return None, model_id, "llm_output_missing_content"

    outline = parsed.get("outline")
    references = parsed.get("references")
    return (
        {
            "section_title": str(parsed.get("section_title") or section_title).strip() or section_title,
            "content": content,
            "outline": outline if isinstance(outline, list) else [],
            "references": references if isinstance(references, list) else [],
            "output_language": SCI_OUTPUT_LANGUAGE,
            "writing_mode": "llm",
        },
        model_id,
        None,
    )


async def build_sci_writing_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    paper_title: str | None = None,
    section_type: str | None = None,
    target_words: int | None = None,
    context_artifact_ids: list[str] | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build SCI writing artifact payload with LLM generation + template fallback."""
    resolved_title = (paper_title or "").strip() or workspace_name or "未命名论文"
    normalized_section_type = _normalize_section_type(section_type)
    resolved_target_words = target_words if isinstance(target_words, int) and target_words > 0 else 1200
    resolved_context_ids = [
        str(artifact_id).strip()
        for artifact_id in (context_artifact_ids or [])
        if str(artifact_id).strip()
    ]
    runtime = get_runtime_state()

    context_summaries = await _load_artifact_context_summaries(
        workspace_id=workspace_id,
        context_artifact_ids=resolved_context_ids,
    )
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "writing-context",
                "kind": "metrics",
                "title": "写作上下文",
                "entries": [
                    {"label": "论文标题", "value": resolved_title},
                    {"label": "章节", "value": _resolve_section_title(normalized_section_type)},
                    {"label": "目标字数", "value": str(resolved_target_words)},
                    {"label": "上下文产物", "value": str(len(context_summaries))},
                ],
            },
        )
        if context_summaries:
            upsert_runtime_block(
                runtime,
                {
                    "id": "context-artifacts",
                    "kind": "list",
                    "title": "上下文产物",
                    "description": "已加载的相关 artifact 摘要",
                    "items": [
                        {
                            "title": str(item.get("title") or "Untitled"),
                            "description": str(item.get("summary") or ""),
                            "meta": str(item.get("type") or ""),
                        }
                        for item in context_summaries[:5]
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="写作上下文已就绪",
            description=f"已加载 {len(context_summaries)} 个 artifact 作为章节写作参考。",
            tone="info",
        )
        advance_runtime_phase(runtime, "prepare", "draft")
        await _emit_bound_runtime(
            message="正在生成章节草稿...",
            current_phase="draft",
            stage_transition=True,
        )

    llm_result, model_id, generation_error = await _try_llm_sci_writing(
        paper_title=resolved_title,
        section_type=normalized_section_type,
        target_words=resolved_target_words,
        context_summaries=context_summaries,
        preferred_model=preferred_model,
    )

    if llm_result is None:
        llm_result = _build_sci_writing_template(
            paper_title=resolved_title,
            section_type=normalized_section_type,
            target_words=resolved_target_words,
        )

    draft_content = str(llm_result.get("content") or "").strip()
    section_title = str(llm_result.get("section_title") or _resolve_section_title(normalized_section_type)).strip()
    outline = llm_result.get("outline")
    references = llm_result.get("references")
    writing_mode = str(llm_result.get("writing_mode") or "template_fallback")
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "draft-preview",
                "kind": "text",
                "title": "草稿预览",
                "description": section_title or _resolve_section_title(normalized_section_type),
                "content": draft_content[:1400],
            },
        )
        if isinstance(references, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "references",
                    "kind": "list",
                    "title": "参考建议",
                    "items": [
                        {"title": str(reference), "description": ""}
                        for reference in references[:6]
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="章节草稿已生成",
            description=f"已生成 {section_title or normalized_section_type} 草稿并整理参考建议。",
            tone="success" if writing_mode == "llm" else "warning",
        )
        advance_runtime_phase(runtime, "draft", "finalize")
        await _emit_bound_runtime(
            message="正在整理章节草稿产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    return {
        "schema_version": SCI_SCHEMA_VERSION,
        "document_type": ArtifactType.PAPER_DRAFT.value,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "paper_title": resolved_title,
        "workspace_name": workspace_name,
        "workspace_description": workspace_description,
        "section_type": normalized_section_type,
        "section_title": section_title or _resolve_section_title(normalized_section_type),
        "target_words": resolved_target_words,
        "word_count": _estimate_word_count(draft_content),
        "content": draft_content,
        "outline": outline if isinstance(outline, list) else [],
        "references": references if isinstance(references, list) else [],
        "context_artifact_ids": resolved_context_ids,
        "context_artifacts_count": len(context_summaries),
        "context_summaries": context_summaries,
        "writing_mode": writing_mode,
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error if writing_mode != "llm" else None,
    }
