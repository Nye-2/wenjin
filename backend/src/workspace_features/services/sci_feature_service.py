"""Service helpers for SCI workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. framework-outline payload assembly,
2. literature search (LLM synthesis),
3. paper analysis (structured method/experiment/conclusion extraction),
4. SCI section-writing payload assembly.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts import ArtifactType
from src.database import get_db_session
from src.services.literature_service import LiteratureService
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
    resolve_writing_model_id,
)

logger = logging.getLogger(__name__)

SCI_SCHEMA_VERSION = "v1"
SCI_OUTPUT_LANGUAGE = "en"


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


async def _try_llm_literature_search(
    *,
    query: str,
    discipline: str,
    existing_literature: list[dict[str, Any]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based literature search synthesis."""
    literature_context = ""
    if existing_literature:
        lit_summaries = []
        for lit in existing_literature[:10]:
            title = lit.get("title", "未知标题")
            year = lit.get("year", "")
            venue = lit.get("venue", "")
            lit_summaries.append(f"- {title} ({year}) - {venue}")
        literature_context = "已有相关文献：\n" + "\n".join(lit_summaries)

    prompt = build_json_prompt(
        instruction="请根据检索需求生成文献检索建议和分析。",
        context_sections=[
            ("检索查询", query),
            ("学科领域", discipline),
            ("已有文献", literature_context or "暂无已有文献"),
        ],
        schema='{"papers":[{"title":"论文标题","authors":["作者1"],"year":2024,"venue":"期刊/会议","abstract":"摘要","relevance":"相关性说明"}],"top_hits":[{"title":"高相关论文","reason":"推荐理由"}],"filters":{"year_range":{"min":2020,"max":2025},"sources":["数据源"],"quartiles":["Q1","Q2"]},"summary":"检索结果综述"}',
        requirements=[
            "papers 数组提供 5-10 条建议条目；无法确认的具体论文需明确标注待核验。",
            "top_hits 提供 3 条最相关命中及推荐理由。",
            "filters 提供合理的筛选维度建议。",
            "summary 提供检索结果综述和研究方向建议。",
        ],
        output_language="zh",
    )
    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是学术文献检索专家。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.3,
    )
    if parsed is None:
        return None, model_id, generation_error

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


def _resolve_generation_model(preferred_model: str | None) -> str | None:
    return resolve_writing_model_id(preferred_model)


def _build_literature_review_template(topic: str, discipline: str) -> dict[str, Any]:
    return {
        "summary": f"围绕 {topic} 的研究已经形成若干稳定方向，但在 {discipline} 语境下仍存在可继续深化的空白。",
        "sections": [
            {
                "title": "研究背景",
                "content": f"说明 {topic} 在 {discipline} 中的重要性、典型问题场景以及研究动因。",
            },
            {
                "title": "代表性路线",
                "content": "归纳经典方法、近期方法和方法演进趋势，对比各路线的适用边界。",
            },
            {
                "title": "研究空白",
                "content": "从数据、方法、评估设置和落地场景四个层面梳理仍未充分解决的问题。",
            },
        ],
        "key_papers": [],
        "research_gaps": [
            "缺少统一评测基准或跨场景验证。",
            "现有方法对真实约束与工程可行性考虑不足。",
            "论文之间的对比口径不完全一致，结论可复用性有限。",
        ],
        "next_actions": [
            "补充 5-10 篇高相关核心文献并标记方法与数据集。",
            "基于研究空白收敛 1-2 个可执行的问题陈述。",
            "将文献综述沉淀为写作大纲的相关工作部分。",
        ],
    }


async def _try_llm_literature_review(
    *,
    topic: str,
    discipline: str,
    literature: list[dict[str, Any]],
    context_summaries: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    model_id = _resolve_generation_model(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"

    literature_lines = [
        f"- {item.get('title', 'Untitled')} ({item.get('year', 'n/a')})"
        for item in literature[:12]
        if isinstance(item, dict)
    ]
    artifact_lines = [
        f"- {item.get('title', 'Untitled')}: {item.get('summary', '')}"
        for item in context_summaries[:5]
    ]
    prompt = build_json_prompt(
        instruction="请生成 SCI 论文可直接复用的文献综述。",
        context_sections=[
            ("主题", topic),
            ("学科", discipline or "综合"),
            ("已有文献信息", "\n".join(literature_lines) if literature_lines else "- 暂无明确文献条目"),
            ("已有上下文产出", "\n".join(artifact_lines) if artifact_lines else "- 暂无上下文产出"),
        ],
        schema='{"summary":"综述摘要","sections":[{"title":"章节标题","content":"章节内容"}],"key_papers":[{"title":"论文标题","reason":"为什么重要"}],"research_gaps":["空白1"],"next_actions":["动作1"]}',
        requirements=[
            "sections 至少覆盖背景、代表性路线和研究空白三个层次。",
            "key_papers 优先使用给定文献；不确定时明确标注待核验。",
            "research_gaps 要具体到可形成问题陈述。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是严谨的学术综述作者。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.2,
    )
    if parsed is None:
        return None, model_id, generation_error
    return parsed, model_id, None


async def build_sci_literature_review_payload(
    *,
    workspace_id: str,
    topic: str,
    discipline: str | None = None,
    context_artifact_ids: list[str] | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build a structured literature review payload for SCI workspaces."""
    resolved_topic = (topic or "").strip() or "研究主题"
    resolved_discipline = _normalize_discipline(discipline)
    context_summaries = await _load_artifact_context_summaries(
        workspace_id=workspace_id,
        context_artifact_ids=context_artifact_ids or [],
    )
    literature = await _load_workspace_literature(workspace_id)
    llm_result, model_id, generation_error = await _try_llm_literature_review(
        topic=resolved_topic,
        discipline=resolved_discipline,
        literature=literature,
        context_summaries=context_summaries,
        preferred_model=preferred_model,
    )
    payload = llm_result or _build_literature_review_template(resolved_topic, resolved_discipline)
    return {
        "schema_version": SCI_SCHEMA_VERSION,
        "document_type": ArtifactType.LITERATURE_REVIEW.value,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "topic": resolved_topic,
        "discipline": resolved_discipline,
        "summary": str(payload.get("summary") or "").strip(),
        "sections": payload.get("sections") if isinstance(payload.get("sections"), list) else [],
        "key_papers": payload.get("key_papers") if isinstance(payload.get("key_papers"), list) else [],
        "research_gaps": payload.get("research_gaps") if isinstance(payload.get("research_gaps"), list) else [],
        "next_actions": payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else [],
        "context_artifact_ids": context_artifact_ids or [],
        "context_artifacts_count": len(context_summaries),
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error,
        "generation_mode": "llm" if llm_result is not None else "template",
    }


def _build_framework_outline_template(
    *,
    paper_title: str,
    topic: str,
) -> dict[str, Any]:
    return {
        "abstract": f"本文围绕 {topic} 展开研究，说明问题背景、方法路线、实验评估与潜在贡献。",
        "keywords": [topic, "methodology", "evaluation"],
        "sections": [
            {"title": "Introduction", "focus": "研究背景、问题定义、贡献概述"},
            {"title": "Related Work", "focus": "已有方法脉络与差异化定位"},
            {"title": "Methodology", "focus": "模型/系统设计与核心机制"},
            {"title": "Experiments", "focus": "数据集、基线、指标与实验设置"},
            {"title": "Results and Discussion", "focus": "结果解读、消融与局限"},
            {"title": "Conclusion", "focus": "总结与未来工作"},
        ],
        "contributions": [
            "给出清晰的问题建模与研究边界。",
            "设计可复用的方法路线与评估方案。",
            "形成可直接进入正文写作的章节框架。",
        ],
    }


async def _try_llm_framework_outline(
    *,
    paper_title: str,
    topic: str,
    context_summaries: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    model_id = _resolve_generation_model(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"

    artifact_lines = [
        f"- {item.get('title', 'Untitled')}: {item.get('summary', '')}"
        for item in context_summaries[:6]
    ]
    prompt = build_json_prompt(
        instruction="请为 SCI 论文生成摘要和章节大纲。",
        context_sections=[
            ("论文题目", paper_title),
            ("研究主题", topic),
            ("上下文产出", "\n".join(artifact_lines) if artifact_lines else "- 暂无上下文"),
        ],
        schema='{"abstract":"摘要","keywords":["kw1"],"sections":[{"title":"Introduction","focus":"..." }],"contributions":["贡献1"]}',
        requirements=[
            "sections 应覆盖 Introduction、Related Work、Methodology、Experiments、Results and Discussion、Conclusion。",
            "contributions 应写成可直接进入论文的贡献点表达。",
            "摘要、关键词和章节 focus 必须彼此一致。",
        ],
        output_language="en",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是学术写作规划助手。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.2,
    )
    if parsed is None:
        return None, model_id, generation_error
    return parsed, model_id, None


async def build_framework_outline_payload(
    *,
    workspace_id: str,
    paper_title: str,
    topic: str,
    context_artifact_ids: list[str] | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build a framework-outline payload for SCI workspaces."""
    resolved_title = (paper_title or "").strip() or "Untitled Paper"
    resolved_topic = (topic or "").strip() or resolved_title
    context_summaries = await _load_artifact_context_summaries(
        workspace_id=workspace_id,
        context_artifact_ids=context_artifact_ids or [],
    )
    llm_result, model_id, generation_error = await _try_llm_framework_outline(
        paper_title=resolved_title,
        topic=resolved_topic,
        context_summaries=context_summaries,
        preferred_model=preferred_model,
    )
    payload = llm_result or _build_framework_outline_template(
        paper_title=resolved_title,
        topic=resolved_topic,
    )
    result = {
        "schema_version": SCI_SCHEMA_VERSION,
        "document_type": ArtifactType.FRAMEWORK_OUTLINE.value,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "paper_title": resolved_title,
        "topic": resolved_topic,
        "abstract": str(payload.get("abstract") or "").strip(),
        "keywords": payload.get("keywords") if isinstance(payload.get("keywords"), list) else [],
        "sections": payload.get("sections") if isinstance(payload.get("sections"), list) else [],
        "contributions": payload.get("contributions") if isinstance(payload.get("contributions"), list) else [],
        "context_artifact_ids": context_artifact_ids or [],
        "context_artifacts_count": len(context_summaries),
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error,
        "generation_mode": "llm" if llm_result is not None else "template",
    }
    return result


def _build_peer_review_template(
    *,
    paper_title: str,
) -> dict[str, Any]:
    return {
        "overall_assessment": f"{paper_title} 已具备基础论文结构，但还需要在问题定义、实验完整性和论证力度上继续加强。",
        "score": 7.2,
        "strengths": [
            "选题具备明确的问题背景与应用价值。",
            "结构完整，便于继续扩展为正式稿件。",
            "已有产出足以支持进一步的实证强化。",
        ],
        "weaknesses": [
            "创新点与已有方法差异需要写得更聚焦。",
            "实验设置和评价指标说明仍偏薄弱。",
            "结论部分还需要结合局限性与未来工作。",
        ],
        "revision_actions": [
            "补一段与主流基线的差异化定位。",
            "补充实验设置、评价指标与消融说明。",
            "将结论改写为“发现 + 局限 + 下一步”结构。",
        ],
    }


async def _try_llm_peer_review(
    *,
    paper_title: str,
    manuscript_excerpt: str,
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    model_id = _resolve_generation_model(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"
    prompt = build_json_prompt(
        instruction="请以审稿人视角评审以下稿件内容。",
        context_sections=[
            ("题目", paper_title),
            ("稿件摘录", _truncate(manuscript_excerpt, 2600)),
        ],
        schema='{"overall_assessment":"总体评价","score":7.5,"strengths":["优点1"],"weaknesses":["问题1"],"revision_actions":["修改建议1"]}',
        requirements=[
            "strengths、weaknesses、revision_actions 都要具体，不要泛泛而谈。",
            "score 使用 0-10 范围内的数字。",
            "revision_actions 应能直接转化为下一轮写作动作。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是严格但建设性的学术审稿人。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.1,
    )
    if parsed is None:
        return None, model_id, generation_error
    return parsed, model_id, None


async def build_peer_review_payload(
    *,
    paper_title: str,
    manuscript_excerpt: str,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build a structured peer-review payload."""
    resolved_title = (paper_title or "").strip() or "Untitled Paper"
    llm_result, model_id, generation_error = await _try_llm_peer_review(
        paper_title=resolved_title,
        manuscript_excerpt=manuscript_excerpt,
        preferred_model=preferred_model,
    )
    payload = llm_result or _build_peer_review_template(paper_title=resolved_title)
    return {
        "schema_version": SCI_SCHEMA_VERSION,
        "document_type": ArtifactType.REVIEW.value,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "paper_title": resolved_title,
        "overall_assessment": str(payload.get("overall_assessment") or "").strip(),
        "score": float(payload.get("score") or 0),
        "strengths": payload.get("strengths") if isinstance(payload.get("strengths"), list) else [],
        "weaknesses": payload.get("weaknesses") if isinstance(payload.get("weaknesses"), list) else [],
        "revision_actions": payload.get("revision_actions") if isinstance(payload.get("revision_actions"), list) else [],
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error,
        "generation_mode": "llm" if llm_result is not None else "template",
    }


def _build_journal_recommend_template(
    *,
    paper_title: str,
) -> dict[str, Any]:
    return {
        "paper_profile": f"{paper_title} 属于具备明确问题背景、方法设计和实验验证的常规 SCI 论文形态。",
        "journals": [
            {
                "name": "Expert Systems with Applications",
                "fit": "适合方法与应用并重的工程类论文。",
                "reason": "偏好有实验验证、应用落地和系统性叙述的稿件。",
            },
            {
                "name": "Knowledge-Based Systems",
                "fit": "适合强调模型设计与决策智能的稿件。",
                "reason": "如果论文突出方法创新和知识建模，可优先考虑。",
            },
            {
                "name": "Applied Sciences",
                "fit": "适合主题交叉、工程验证充分的稿件。",
                "reason": "当投稿策略偏向稳妥和快速时可作为保守选项。",
            },
        ],
        "submission_notes": [
            "摘要中需要突出问题、方法、实验结果三段式信息。",
            "投稿前补齐与目标期刊近三年同类论文的对比定位。",
        ],
    }


async def _try_llm_journal_recommend(
    *,
    paper_title: str,
    abstract: str,
    discipline: str,
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    model_id = _resolve_generation_model(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"
    prompt = build_json_prompt(
        instruction="请根据论文题目和摘要推荐投稿期刊。",
        context_sections=[
            ("题目", paper_title),
            ("学科", discipline),
            ("摘要", _truncate(abstract, 2400)),
        ],
        schema='{"paper_profile":"论文画像","journals":[{"name":"期刊","fit":"适配度","reason":"推荐原因"}],"submission_notes":["建议1"]}',
        requirements=[
            "journals 至少给出 3 个候选期刊。",
            "fit 和 reason 必须具体到论文主题、方法或实验形态。",
            "submission_notes 给出投稿前仍需补强的点。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是审稿策略顾问。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.2,
    )
    if parsed is None:
        return None, model_id, generation_error
    return parsed, model_id, None


async def build_journal_recommend_payload(
    *,
    paper_title: str,
    abstract: str,
    discipline: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build a structured journal-recommendation payload."""
    resolved_title = (paper_title or "").strip() or "Untitled Paper"
    resolved_discipline = _normalize_discipline(discipline)
    llm_result, model_id, generation_error = await _try_llm_journal_recommend(
        paper_title=resolved_title,
        abstract=abstract,
        discipline=resolved_discipline,
        preferred_model=preferred_model,
    )
    payload = llm_result or _build_journal_recommend_template(paper_title=resolved_title)
    return {
        "schema_version": SCI_SCHEMA_VERSION,
        "document_type": ArtifactType.SUMMARY.value,
        "output_language": SCI_OUTPUT_LANGUAGE,
        "paper_title": resolved_title,
        "discipline": resolved_discipline,
        "paper_profile": str(payload.get("paper_profile") or "").strip(),
        "journals": payload.get("journals") if isinstance(payload.get("journals"), list) else [],
        "submission_notes": payload.get("submission_notes") if isinstance(payload.get("submission_notes"), list) else [],
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error,
        "generation_mode": "llm" if llm_result is not None else "template",
    }


async def build_literature_search_payload(
    *,
    workspace_id: str,
    query: str,
    discipline: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build literature search artifact content with LLM synthesis.

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

    if runtime is not None:
        append_runtime_activity(
            runtime,
            title="检索失败",
            description=f"模型未返回结构化检索结果：{generation_error or 'unknown_error'}",
            tone="error",
        )
        advance_runtime_phase(runtime, "retrieve", "finalize")
        await _emit_bound_runtime(
            message="文献检索失败，正在回传错误信息...",
            current_phase="finalize",
            stage_transition=True,
        )
    raise RuntimeError(
        f"literature_search_llm_failed: {generation_error or 'unknown_error'}"
    )


async def _try_llm_paper_analysis(
    *,
    paper_title: str,
    paper_abstract: str | None = None,
    paper_content: str | None = None,
    preferred_model: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based paper analysis."""
    model_id = resolve_writing_model_id(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"

    # Build context from paper info
    context_parts = [f"论文标题：{paper_title}"]
    if paper_abstract:
        context_parts.append(f"摘要：{paper_abstract}")
    if paper_content:
        context_parts.append(f"内容片段：{_truncate(paper_content, max_len=2000)}")

    prompt = build_json_prompt(
        instruction="请对以下论文进行结构化分析。",
        context_sections=[("论文上下文", context_parts)],
        schema='{"sections":{"methodology":{"title":"研究方法","content":"方法描述","key_points":["要点1","要点2"]},"experiments":{"title":"实验设计","content":"实验描述","key_points":["要点1"]},"conclusions":{"title":"研究结论","content":"结论描述","key_points":["要点1"]},"innovations":{"title":"创新点","content":"创新描述","key_points":["要点1"]}},"summary":"论文整体评价","quality_assessment":{"methodology_rigor":"高/中/低","experiment_completeness":"高/中/低","contribution_level":"高/中/低"},"recommendations":["后续研究建议1","建议2"]}',
        requirements=[
            "methodology 分析研究方法、技术路线和数据来源。",
            "experiments 分析实验设计、基准和评价指标。",
            "conclusions 总结主要发现和研究贡献。",
            "innovations 提炼核心创新点和理论贡献。",
            "summary 提供 100-200 字的整体评价。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是学术论文分析专家。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.3,
    )
    if parsed is None:
        return None, model_id, generation_error

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
    """Build paper analysis artifact content with LLM analysis.

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

    if runtime is not None:
        append_runtime_activity(
            runtime,
            title="分析失败",
            description=f"模型未返回结构化分析：{generation_error or 'unknown_error'}",
            tone="error",
        )
        advance_runtime_phase(runtime, "analyze", "finalize")
        await _emit_bound_runtime(
            message="论文分析失败，正在回传错误信息...",
            current_phase="finalize",
            stage_transition=True,
        )
    raise RuntimeError(
        f"paper_analysis_llm_failed: {generation_error or 'unknown_error'}"
    )


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


async def _try_llm_sci_writing(
    *,
    paper_title: str,
    section_type: str,
    target_words: int,
    context_summaries: list[dict[str, str]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM-based SCI section writing."""
    model_id = resolve_writing_model_id(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"

    section_title = _resolve_section_title(section_type)
    context_lines = []
    for item in context_summaries[:5]:
        context_lines.append(
            f"- [{item.get('type', 'artifact')}] {item.get('title', 'Untitled')}: {item.get('summary', '')}"
        )
    context_block = "\n".join(context_lines) if context_lines else "- No usable context artifacts."

    prompt = build_json_prompt(
        instruction="Write a SCI paper section draft.",
        context_sections=[
            ("Paper title", paper_title),
            ("Section type", section_type),
            ("Section title", section_title),
            ("Target length", f"around {target_words} words"),
            ("Available context summaries", context_block),
        ],
        schema='{"section_title":"Section Title","content":"Section body in English","outline":["Subsection 1","Subsection 2"],"references":["Reference suggestion 1","Reference suggestion 2"]}',
        requirements=[
            "content must be directly editable academic prose in English.",
            "Maintain a rigorous, specific academic tone.",
            "If context lacks evidence, keep the prose conservative and use references for supplemental suggestions only.",
        ],
        output_language="en",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="You are a SCI writing assistant.",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.4,
    )
    if parsed is None:
        return None, model_id, generation_error

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
    """Build SCI writing artifact payload with LLM generation."""
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
        if runtime is not None:
            append_runtime_activity(
                runtime,
                title="章节写作失败",
                description=f"模型未返回有效章节草稿：{generation_error or 'unknown_error'}",
                tone="error",
            )
            advance_runtime_phase(runtime, "draft", "finalize")
            await _emit_bound_runtime(
                message="章节写作失败，正在回传错误信息...",
                current_phase="finalize",
                stage_transition=True,
            )
        raise RuntimeError(
            f"sci_writing_llm_failed: {generation_error or 'unknown_error'}"
        )

    draft_content = str(llm_result.get("content") or "").strip()
    section_title = str(llm_result.get("section_title") or _resolve_section_title(normalized_section_type)).strip()
    outline = llm_result.get("outline")
    references = llm_result.get("references")
    writing_mode = str(llm_result.get("writing_mode") or "llm")
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
            tone="success",
        )
        advance_runtime_phase(runtime, "draft", "finalize")
        await _emit_bound_runtime(
            message="正在整理章节草稿产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    result = {
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
        "generation_error": None,
    }
    return result
