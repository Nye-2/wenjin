"""Service helpers for SCI workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. framework-outline payload assembly,
2. literature search (Semantic Scholar retrieval + grounded synthesis),
3. paper analysis (structured method/experiment/conclusion extraction),
4. SCI section-writing payload assembly.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.academic.literature import LiteratureSearchService
from src.academic.services.artifact_service import ArtifactService
from src.artifacts import ArtifactType
from src.database import get_db_session
from src.services.references import ReferenceEvidenceService, ReferenceImportService, WorkspaceReferenceService
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
SCI_LITERATURE_SEARCH_SCHEMA_VERSION = "semantic_scholar_v1"
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


async def _load_workspace_references(workspace_id: str) -> list[dict[str, Any]]:
    """Load Reference Library records from workspace for context enrichment."""
    try:
        async with get_db_session() as db:
            service = WorkspaceReferenceService(db)
            response = await service.list_references(workspace_id, offset=0, limit=100)
    except Exception as exc:
        logger.warning(
            "Failed to load workspace references for '%s', fallback to empty context: %s",
            workspace_id,
            exc,
        )
        return []

    items = response.get("items")
    return items if isinstance(items, list) else []


def _format_verified_papers_for_prompt(verified_papers: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, paper in enumerate(verified_papers[:15], start=1):
        title = str(paper.get("title") or "Untitled").strip()
        year = str(paper.get("year") or "n/a")
        venue = str(paper.get("venue") or "").strip()
        doi = str(paper.get("doi") or "").strip()
        external_id = str(paper.get("external_id") or "").strip()
        citations = paper.get("citations_count")
        abstract = _truncate(str(paper.get("abstract") or "").strip(), 520)
        meta = ", ".join(
            part
            for part in [
                f"year={year}",
                f"venue={venue}" if venue else "",
                f"citations={citations}" if citations is not None else "",
                f"doi={doi}" if doi else "",
                f"semantic_scholar_id={external_id}" if external_id else "",
            ]
            if part
        )
        lines.append(f"{index}. {title} ({meta})\nAbstract: {abstract or 'n/a'}")
    return "\n\n".join(lines) if lines else "未检索到 Semantic Scholar 已验证论文。"


def _build_literature_synthesis_template(
    *,
    query: str,
    discipline: str,
    verified_papers: list[dict[str, Any]],
) -> dict[str, Any]:
    titles = [str(item.get("title") or "").strip() for item in verified_papers[:5]]
    titles = [title for title in titles if title]
    if verified_papers:
        summary = f"Semantic Scholar 已围绕“{query}”返回 {len(verified_papers)} 篇可核验论文，可先按引用量、年份和摘要相关性筛选精读对象。"
    else:
        summary = f"Semantic Scholar 暂未围绕“{query}”返回可核验论文，需要调整关键词或缩小/扩大研究范围。"
    return {
        "summary": summary,
        "themes": [
            {
                "name": "已验证检索结果",
                "description": f"当前结果全部来自 Semantic Scholar 元数据；学科上下文：{discipline}。",
                "supporting_external_ids": [
                    str(item.get("external_id"))
                    for item in verified_papers[:5]
                    if item.get("external_id")
                ],
            }
        ] if verified_papers else [],
        "research_gaps": [],
        "recommended_reading_order": [
            {
                "title": title,
                "reason": "先核对摘要、方法和引用关系，再决定是否导入精读。"
            }
            for title in titles
        ],
    }


def _normalize_verified_title(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sanitize_literature_synthesis(
    synthesis: dict[str, Any],
    *,
    verified_papers: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed_ids = {
        str(item.get("external_id") or "").strip()
        for item in verified_papers
        if item.get("external_id")
    }
    allowed_titles = {
        _normalize_verified_title(str(item.get("title") or ""))
        for item in verified_papers
        if str(item.get("title") or "").strip()
    }

    sanitized_order: list[dict[str, Any]] = []
    raw_order = synthesis.get("recommended_reading_order")
    if isinstance(raw_order, list):
        for item in raw_order:
            if not isinstance(item, dict):
                continue
            external_id = str(item.get("external_id") or "").strip()
            title = str(item.get("title") or "").strip()
            if (external_id and external_id in allowed_ids) or (_normalize_verified_title(title) in allowed_titles):
                sanitized_order.append(item)

    sanitized_themes: list[dict[str, Any]] = []
    raw_themes = synthesis.get("themes")
    if isinstance(raw_themes, list):
        for item in raw_themes:
            if not isinstance(item, dict):
                continue
            theme = dict(item)
            supporting_ids = theme.get("supporting_external_ids")
            if isinstance(supporting_ids, list):
                theme["supporting_external_ids"] = [
                    str(external_id)
                    for external_id in supporting_ids
                    if str(external_id) in allowed_ids
                ]
            sanitized_themes.append(theme)

    return {
        "summary": str(synthesis.get("summary") or "").strip(),
        "themes": sanitized_themes,
        "research_gaps": synthesis.get("research_gaps") if isinstance(synthesis.get("research_gaps"), list) else [],
        "recommended_reading_order": sanitized_order,
    }


async def _try_llm_literature_synthesis(
    *,
    query: str,
    discipline: str,
    verified_papers: list[dict[str, Any]],
    existing_literature: list[dict[str, Any]],
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None, str | None]:
    """Synthesize findings strictly from Semantic Scholar verified papers."""
    model_id = _resolve_generation_model(preferred_model)
    if model_id is None:
        return None, [], None, "no_generation_model_configured"

    existing_context = ""
    if existing_literature:
        lit_summaries = []
        for lit in existing_literature[:10]:
            title = lit.get("title", "未知标题")
            year = lit.get("year", "")
            venue = lit.get("venue", "")
            lit_summaries.append(f"- {title} ({year}) - {venue}")
        existing_context = "已有相关文献：\n" + "\n".join(lit_summaries)

    prompt = build_json_prompt(
        instruction="请基于 Semantic Scholar 已验证论文生成文献检索综合分析。",
        context_sections=[
            ("检索查询", query),
            ("学科领域", discipline),
            ("Semantic Scholar 已验证论文", _format_verified_papers_for_prompt(verified_papers)),
            ("已有工作区文献", existing_context or "暂无已有文献"),
        ],
        schema='{"summary":"基于已验证论文的检索综述","themes":[{"name":"主题","description":"主题说明","supporting_external_ids":["Semantic Scholar paperId"]}],"research_gaps":["只基于已验证论文可见证据提出的空白"],"recommended_reading_order":[{"external_id":"Semantic Scholar paperId","title":"已验证论文标题","reason":"推荐精读理由"}],"unverified_leads":[{"lead":"后续检索关键词/方向，不是论文条目","reason":"为什么需要继续检索","next_query":"建议下一轮 Semantic Scholar 查询"}]}',
        requirements=[
            "不得新增、编造或改写任何论文条目；论文只能来自 Semantic Scholar 已验证论文。",
            "recommended_reading_order 只能引用已验证论文中的 title/external_id。",
            "themes 和 research_gaps 必须明确受限于已验证论文的可见摘要与元数据。",
            "unverified_leads 只能写关键词、概念、作者群或下一轮检索式，不得写成论文引用。",
        ],
        output_language="zh",
    )
    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的证据驱动文献分析专家。你只能基于 Semantic Scholar 已验证论文做综合，不允许生成未验证论文条目。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.2,
    )
    if parsed is None:
        return None, [], model_id, generation_error

    synthesis = _sanitize_literature_synthesis(
        {
            "summary": str(parsed.get("summary") or "").strip(),
            "themes": parsed.get("themes") if isinstance(parsed.get("themes"), list) else [],
            "research_gaps": parsed.get("research_gaps") if isinstance(parsed.get("research_gaps"), list) else [],
            "recommended_reading_order": parsed.get("recommended_reading_order") if isinstance(parsed.get("recommended_reading_order"), list) else [],
        },
        verified_papers=verified_papers,
    )
    unverified_leads = parsed.get("unverified_leads") if isinstance(parsed.get("unverified_leads"), list) else []
    return synthesis, cast(list[dict[str, Any]], unverified_leads), model_id, None


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
        system_prompt="你是问津 Compute 的学术综述作者，负责把已有文献和工作区产物综合成可落稿的 Related Work 结构。",
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
    literature = await _load_workspace_references(workspace_id)
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
        system_prompt="你是问津 Compute 的 SCI 写作规划专家，负责生成摘要、贡献点和章节框架，而不是重启需求访谈。",
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
        system_prompt="你是问津 Compute 的学术审稿人，负责输出可执行修订动作，优先指出会影响接收概率的实质问题。",
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
        system_prompt="你是问津 Compute 的投稿策略顾问，负责基于论文画像给出候选期刊和待核验投稿风险。",
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
    """Build literature search artifact content from Semantic Scholar evidence.

    Args:
        workspace_id: UUID of the workspace
        query: Search query string
        discipline: Academic discipline for context
        preferred_model: Optional model ID for generation

    Returns:
        Structured Semantic Scholar grounded literature search result payload
    """
    normalized_query = (query or "").strip()
    if not normalized_query:
        normalized_query = "研究主题"

    normalized_discipline = _normalize_discipline(discipline)
    runtime = get_runtime_state()

    # Load existing literature for context
    existing_literature = await _load_workspace_references(workspace_id)
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
            message="正在检索 Semantic Scholar 已验证论文...",
            current_phase="retrieve",
            stage_transition=True,
        )

    search_service = LiteratureSearchService()
    retrieval_result = await search_service.search(
        query=normalized_query,
        discipline=normalized_discipline,
        limit=10,
    )
    verified_papers = retrieval_result.get("verified_papers")
    if not isinstance(verified_papers, list):
        verified_papers = []
    retrieval = retrieval_result.get("retrieval")
    retrieval_info = retrieval if isinstance(retrieval, dict) else {}

    reference_import: dict[str, Any] = {"imported": 0, "created": 0, "items": []}
    if verified_papers:
        try:
            async with get_db_session() as db:
                reference_import = await ReferenceImportService(db).import_semantic_scholar_papers(
                    workspace_id=workspace_id,
                    papers=verified_papers,
                    source_label=f"Literature search: {normalized_query}",
                )
        except Exception as exc:
            logger.warning(
                "Failed to import Semantic Scholar results into reference library for workspace %s: %s",
                workspace_id,
                exc,
                exc_info=True,
            )
            reference_import = {
                "imported": 0,
                "created": 0,
                "items": [],
                "error": str(exc),
            }

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "verified-papers",
                "kind": "list",
                "title": "Semantic Scholar 已验证论文",
                "description": "以下条目来自 Semantic Scholar 元数据，不包含模型生成论文。",
                "items": [
                    {
                        "title": str(item.get("title") or "Untitled"),
                        "description": _truncate(str(item.get("abstract") or ""), 220),
                        "meta": str(item.get("venue") or item.get("doi") or item.get("external_id") or ""),
                        "badge": str(item.get("year") or "") or None,
                    }
                    for item in verified_papers[:6]
                    if isinstance(item, dict)
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="Semantic Scholar 检索完成",
            description=(
                f"已核验 {len(verified_papers)} 篇论文，"
                f"其中 {int(reference_import.get('imported') or 0)} 篇已同步到参考库。"
            ),
            tone="success" if retrieval_info.get("status") == "ok" else "warning",
        )

    synthesis, unverified_leads, model_id, generation_error = await _try_llm_literature_synthesis(
        query=normalized_query,
        discipline=normalized_discipline,
        verified_papers=verified_papers,
        existing_literature=existing_literature,
        preferred_model=preferred_model,
    )
    generation_mode = "semantic_scholar_grounded_llm" if synthesis is not None else "semantic_scholar_metadata"
    if synthesis is None:
        synthesis = _build_literature_synthesis_template(
            query=normalized_query,
            discipline=normalized_discipline,
            verified_papers=verified_papers,
        )

    payload = {
        "schema_version": SCI_LITERATURE_SEARCH_SCHEMA_VERSION,
        "document_type": ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        "output_language": "zh",
        "query": normalized_query,
        "discipline": normalized_discipline,
        "source": "semantic_scholar",
        "retrieval": retrieval_info,
        "verified_papers": verified_papers,
        "model_synthesis": synthesis,
        "unverified_leads": unverified_leads,
        "reference_import": {
            "imported": int(reference_import.get("imported") or 0),
            "created": int(reference_import.get("created") or 0),
            "error": reference_import.get("error"),
        },
        "existing_literature_count": len(existing_literature),
        "generated_at": _utc_now_iso(),
        "model_id": model_id,
        "generation_error": generation_error,
        "generation_mode": generation_mode,
    }

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "result-summary",
                "kind": "metrics",
                "title": "检索结果",
                "entries": [
                    {"label": "已验证论文", "value": str(len(verified_papers))},
                    {"label": "已入参考库", "value": str(int(reference_import.get("imported") or 0))},
                    {"label": "未验证线索", "value": str(len(unverified_leads))},
                    {"label": "事实来源", "value": "Semantic Scholar"},
                    {"label": "生成模式", "value": generation_mode},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="文献检索产物完成",
            description="已将 Semantic Scholar 结果和基于证据的综合分析写入产物。",
            tone="success",
        )
        advance_runtime_phase(runtime, "retrieve", "finalize")
        await _emit_bound_runtime(
            message="正在整理文献检索产物...",
            current_phase="finalize",
            stage_transition=True,
        )
    return payload


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
        system_prompt="你是问津 Compute 的论文分析专家，负责基于给定论文上下文拆解方法、实验、结论和创新点。",
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
    reference_id: str | None = None,
    paper_title: str | None = None,
    paper_abstract: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build paper analysis artifact content with LLM analysis.

    Args:
        workspace_id: UUID of the workspace
        reference_id: Optional reference-library ID for context
        paper_title: Paper title (required if reference_id not provided)
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

    # Try to load more reference context if reference_id is provided
    paper_content = None
    if reference_id:
        try:
            async with get_db_session() as db:
                service = WorkspaceReferenceService(db)
                reference = await service.get(workspace_id, reference_id)
                if reference:
                    resolved_title = reference.title or resolved_title
                    paper_abstract = reference.abstract or paper_abstract
        except Exception as e:
            logger.warning("Failed to load reference %s: %s", reference_id, e)

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "paper-context",
                "kind": "metrics",
                "title": "论文上下文",
                "entries": [
                    {"label": "标题", "value": resolved_title},
                    {"label": "Reference ID", "value": reference_id or "未提供"},
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
        llm_result["reference_id"] = reference_id
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
        verified_papers = content.get("verified_papers")
        verified_count = len(verified_papers) if isinstance(verified_papers, list) else 0
        return f"文献检索主题：{query or '未命名主题'}；Semantic Scholar 已验证论文 {verified_count} 篇。"
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
    evidence_units: list[dict[str, Any]],
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

    evidence_lines = []
    for unit in evidence_units[:8]:
        if not isinstance(unit, dict):
            continue
        ref_title = str(unit.get("reference_title") or unit.get("title") or "Unknown")
        section = str(unit.get("section_title") or unit.get("unit_type") or "")
        content = str(unit.get("content") or "")[:500]
        evidence_lines.append(f"- [{ref_title}] {section}: {content}")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "- No evidence units available."

    prompt = build_json_prompt(
        instruction="Write a SCI paper section draft.",
        context_sections=[
            ("Paper title", paper_title),
            ("Section type", section_type),
            ("Section title", section_title),
            ("Target length", f"around {target_words} words"),
            ("Available context summaries", context_block),
            ("Reference text units (grounded evidence)", evidence_block),
        ],
        schema='{"section_title":"Section Title","content":"Section body in English","outline":["Subsection 1","Subsection 2"],"references":["Reference suggestion 1","Reference suggestion 2"]}',
        requirements=[
            "content must be directly editable academic prose in English.",
            "Maintain a rigorous, specific academic tone.",
            "Ground claims in the provided reference text units when possible.",
            "Use citation keys from the Reference Library; do not invent citations.",
        ],
        output_language="en",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="You are Wenjin Compute's SCI writing specialist. Produce evidence-aware, directly editable academic prose from the provided workspace context; do not invent citations or results.",
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

    evidence_units: list[dict[str, Any]] = []
    try:
        async with get_db_session() as db:
            evidence = await ReferenceEvidenceService(db).build_evidence_pack(
                workspace_id=workspace_id,
                query=f"{resolved_title} {normalized_section_type}",
                max_units=8,
            )
            evidence_units = evidence.get("selected_units", [])
            if evidence_units and runtime is not None:
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "evidence-pack",
                        "kind": "list",
                        "title": "文献证据包",
                        "description": "从 Reference Library 召回的相关文本片段",
                        "items": [
                            {
                                "title": str(u.get("reference_title") or u.get("title") or "未知文献"),
                                "description": str(u.get("section_title") or u.get("unit_type") or "")[:80],
                                "meta": f"{len(str(u.get('content') or ''))} chars",
                            }
                            for u in evidence_units[:5]
                            if isinstance(u, dict)
                        ],
                    },
                )
    except Exception:
        logger.debug(
            "Evidence pack load failed for workspace=%s section=%s",
            workspace_id,
            normalized_section_type,
            exc_info=True,
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
        evidence_units=evidence_units,
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
