"""Thesis writing service for LLM-native outline/chapter generation."""

from __future__ import annotations

import logging
from typing import Any

from src.artifacts import ArtifactType
from src.database import get_db_session
from src.services.references import ReferenceEvidenceService
from src.workspace_features.services.llm_json import (
    build_json_prompt,
    invoke_json_chat_model,
)

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_str_list(value: Any, *, max_items: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value:
        text = str(raw or "").strip()
        if text:
            result.append(text)
        if len(result) >= max_items:
            break
    return result

def _summarize_deep_research_ideas(raw: Any, *, max_items: int = 8) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, str]] = []
    for index, candidate in enumerate(raw, start=1):
        if len(items) >= max_items:
            break

        if isinstance(candidate, dict):
            title = str(candidate.get("title") or "").strip() or f"研究构想 {index}"
            description = str(
                candidate.get("description")
                or candidate.get("novelty_assessment")
                or ""
            ).strip()
        else:
            text = str(candidate or "").strip()
            if not text:
                continue
            title = text[:48]
            description = text

        items.append({"title": title, "description": description})
    return items


def _summarize_deep_research_gaps(raw: Any, *, max_items: int = 6) -> list[str]:
    if not isinstance(raw, list):
        return []

    result: list[str] = []
    for candidate in raw:
        if len(result) >= max_items:
            break
        if isinstance(candidate, dict):
            text = str(candidate.get("description") or "").strip()
        else:
            text = str(candidate or "").strip()
        if text:
            result.append(text)
    return result


async def _load_deep_research_snapshot(
    *,
    workspace_id: str | None,
    artifact_ids: list[str] | None,
) -> dict[str, Any]:
    if not workspace_id:
        return {
            "artifact_ids": [],
            "idea_items": [],
            "gap_highlights": [],
        }

    target_ids = {str(item).strip() for item in (artifact_ids or []) if str(item).strip()}

    try:
        from src.academic.services import ArtifactService
        from src.database import get_db_session
    except Exception:
        return {
            "artifact_ids": sorted(target_ids),
            "idea_items": [],
            "gap_highlights": [],
        }

    try:
        async with get_db_session() as db:
            service = ArtifactService(db)
            artifacts = await service.list_by_workspace(workspace_id=workspace_id, limit=300)
    except Exception:
        logger.exception("Failed to load deep research snapshot for thesis writing")
        return {
            "artifact_ids": sorted(target_ids),
            "idea_items": [],
            "gap_highlights": [],
        }

    candidates: list[Any] = []
    for artifact in artifacts:
        if target_ids and str(artifact.id) not in target_ids:
            continue
        if artifact.type != ArtifactType.DEEP_RESEARCH_REPORT.value:
            continue
        content = artifact.content if isinstance(artifact.content, dict) else {}
        if not isinstance(content, dict) or not content:
            continue
        candidates.append(artifact)

    selected_ids = [str(item.id) for item in candidates] or sorted(target_ids)
    idea_items: list[dict[str, str]] = []
    gap_highlights: list[str] = []

    for artifact in candidates:
        content = artifact.content if isinstance(artifact.content, dict) else {}
        idea_items.extend(_summarize_deep_research_ideas(content.get("ideas"), max_items=12))
        gap_highlights.extend(_summarize_deep_research_gaps(content.get("gaps"), max_items=10))

    # Deduplicate while preserving order
    dedup_ideas: list[dict[str, str]] = []
    seen_idea_titles: set[str] = set()
    for item in idea_items:
        key = item["title"].strip().lower()
        if not key or key in seen_idea_titles:
            continue
        seen_idea_titles.add(key)
        dedup_ideas.append(item)
        if len(dedup_ideas) >= 8:
            break

    dedup_gaps: list[str] = []
    seen_gap_keys: set[str] = set()
    for gap_item in gap_highlights:
        key = gap_item.strip().lower()
        if not key or key in seen_gap_keys:
            continue
        seen_gap_keys.add(key)
        dedup_gaps.append(gap_item)
        if len(dedup_gaps) >= 6:
            break

    return {
        "artifact_ids": selected_ids,
        "idea_items": dedup_ideas,
        "gap_highlights": dedup_gaps,
    }


async def _invoke_json_llm(
    *,
    system_prompt: str,
    prompt: str,
    preferred_model: str | None,
    temperature: float = 0.3,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt=system_prompt,
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=temperature,
    )
    if parsed is None and generation_error and generation_error.startswith("llm_generation_failed"):
        logger.exception("Thesis writing LLM call failed: %s", generation_error)
    return parsed, model_id, generation_error


def _normalize_outline(raw_outline: dict[str, Any], *, target_words: int) -> dict[str, Any]:
    chapters = raw_outline.get("chapters")
    normalized_chapters: list[dict[str, Any]] = []
    fallback_words = max(1000, target_words // 6)

    if isinstance(chapters, list):
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            normalized_chapters.append(
                {
                    "title": str(chapter.get("title") or f"第{index}章"),
                    "position": str(chapter.get("position") or "正文"),
                    "targetWords": max(800, _safe_int(chapter.get("targetWords"), fallback_words)),
                    "keyPoints": _clean_str_list(chapter.get("keyPoints"), max_items=8),
                    "sections": _clean_str_list(chapter.get("sections"), max_items=10),
                }
            )

    return {
        "abstract": str(raw_outline.get("abstract") or "").strip(),
        "keywords": _clean_str_list(raw_outline.get("keywords"), max_items=8),
        "chapters": normalized_chapters,
    }


async def build_outline_payload(
    *,
    paper_title: str,
    target_words: int = 20000,
    literature_count: int = 0,
    deep_research_artifact_ids: list[str] | None = None,
    workspace_id: str | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build thesis outline via LLM only."""
    deep_research_snapshot = await _load_deep_research_snapshot(
        workspace_id=workspace_id,
        artifact_ids=deep_research_artifact_ids,
    )
    idea_items = (
        deep_research_snapshot.get("idea_items")
        if isinstance(deep_research_snapshot.get("idea_items"), list)
        else []
    )
    gap_highlights = (
        deep_research_snapshot.get("gap_highlights")
        if isinstance(deep_research_snapshot.get("gap_highlights"), list)
        else []
    )

    ideas_text = "\n".join(
        f"- {item.get('title')}: {item.get('description')}"
        for item in idea_items
        if isinstance(item, dict)
    ) or "- 无"
    gaps_text = "\n".join(f"- {item}" for item in gap_highlights) or "- 无"

    prompt = build_json_prompt(
        instruction="请生成一份可直接用于毕业论文写作的结构化大纲。",
        context_sections=[
            ("论文题目", paper_title),
            ("目标总字数", str(target_words)),
            ("当前文献数量", str(literature_count)),
            (
                "Deep Research 上下文",
                [
                    f"- 产物数量：{len(deep_research_snapshot.get('artifact_ids') or [])}",
                    f"- 研究构想：\n{ideas_text}",
                    f"- 研究空白：\n{gaps_text}",
                ],
            ),
        ],
        schema=(
            '{"abstract":"中文摘要","keywords":["关键词1","关键词2"],'
            '"chapters":[{"title":"章节标题","position":"本章定位","targetWords":3000,'
            '"keyPoints":["要点1","要点2"],"sections":["1.1 小节","1.2 小节"]}]}'
        ),
        requirements=[
            "章节应覆盖绪论、相关工作、方法、实验、结论等完整链路。",
            "尽量吸收并体现已有 Deep Research 构想与研究空白。",
            "每章给出清晰定位与可执行小节结构。",
            "targetWords 总体应接近目标总字数。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await _invoke_json_llm(
        system_prompt="你是问津 Compute 的学位论文大纲专家，负责把题目、调研产物和文献线索转成可执行章节结构。",
        prompt=prompt,
        preferred_model=preferred_model,
    )
    if parsed is None:
        raise RuntimeError(f"outline_generation_failed: {generation_error or 'unknown_error'}")

    outline = _normalize_outline(parsed, target_words=target_words)
    if not outline["chapters"]:
        raise RuntimeError("outline_generation_failed: llm_output_missing_chapters")

    return {
        "paper_title": paper_title,
        "outline": outline,
        "generation_mode": "llm",
        "model_id": model_id,
        "source_context": {
            "literature_count": literature_count,
            "deep_research_artifact_ids": deep_research_snapshot.get("artifact_ids") or [],
            "deep_research_idea_titles": [
                str(item.get("title") or "").strip()
                for item in idea_items
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ],
            "deep_research_gap_highlights": [str(item) for item in gap_highlights if str(item).strip()],
        },
        "schema_version": "v1",
    }


async def build_chapter_payload(
    *,
    workspace_id: str | None = None,
    paper_title: str,
    chapter_index: int,
    chapter_title: str,
    target_words: int = 2500,
    references_used: list[str] | None = None,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build thesis chapter draft via LLM only.

    When ``workspace_id`` is provided, the function loads an evidence pack
    from the workspace Reference Library so the LLM can ground citations in
    actual text units rather than title lists alone.
    """
    normalized_refs = [str(ref).strip() for ref in (references_used or []) if str(ref).strip()]
    refs_text = "\n".join(f"- {ref}" for ref in normalized_refs[:20]) or "- 无明确参考文献"

    evidence_sections: list[tuple[str, str]] = []
    if workspace_id:
        try:
            async with get_db_session() as db:
                evidence = await ReferenceEvidenceService(db).build_evidence_pack(
                    workspace_id=workspace_id,
                    query=chapter_title,
                    max_units=8,
                )
                selected_units = evidence.get("selected_units", [])
                if selected_units:
                    evidence_lines = []
                    for unit in selected_units[:8]:
                        if not isinstance(unit, dict):
                            continue
                        ref_title = str(unit.get("reference_title") or unit.get("title") or "未知文献")
                        section = str(unit.get("section_title") or unit.get("unit_type") or "")
                        content = str(unit.get("content") or "")[:600]
                        evidence_lines.append(f"- [{ref_title}] {section}: {content}")
                    evidence_sections.append(("参考文本片段", "\n".join(evidence_lines)))
                outline = evidence.get("library_outline", [])
                if outline:
                    evidence_sections.append(
                        ("文献库概览", f"工作区共有 {len(outline)} 篇文献可供引用")
                    )
        except Exception:
            logger.debug(
                "Evidence pack load failed for workspace=%s chapter=%s",
                workspace_id,
                chapter_title,
                exc_info=True,
            )

    context_sections = [
        ("论文题目", paper_title),
        ("章节序号", str(chapter_index + 1)),
        ("章节标题", chapter_title),
        ("目标字数", str(target_words)),
        ("可用参考线索", refs_text),
    ]
    context_sections.extend(evidence_sections)

    prompt = build_json_prompt(
        instruction="请撰写毕业论文单章节草稿。",
        context_sections=context_sections,
        schema='{"markdown":"完整章节 Markdown","estimated_words":2300,"references_used":["参考1","参考2"]}',
        requirements=[
            "markdown 必须是可直接落库的章节正文，包含标题和若干小节。",
            "内容具备学术写作风格，避免口语化表达。",
            "estimated_words 为正文实际估算字数。",
            "引用必须使用 Reference Library 中提供的 citation_key，禁止编造引用。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await _invoke_json_llm(
        system_prompt="你是问津 Compute 的学位论文章节写作专家，负责输出可落库章节草稿并标注证据缺口。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.35,
    )
    if parsed is None:
        raise RuntimeError(f"chapter_generation_failed: {generation_error or 'unknown_error'}")

    markdown = str(parsed.get("markdown") or parsed.get("content") or "").strip()
    if not markdown:
        raise RuntimeError("chapter_generation_failed: llm_output_missing_markdown")
    if not markdown.lstrip().startswith("#"):
        markdown = f"# {chapter_title}\n\n{markdown}"

    estimated_words = max(500, _safe_int(parsed.get("estimated_words"), int(target_words * 0.85)))
    used_references = _clean_str_list(parsed.get("references_used"), max_items=20) or normalized_refs

    return {
        "paper_title": paper_title,
        "chapter_index": chapter_index,
        "chapter_title": chapter_title,
        "target_words": target_words,
        "estimated_words": estimated_words,
        "markdown": markdown,
        "references_used": used_references,
        "generation_mode": "llm",
        "model_id": model_id,
        "schema_version": "v1",
    }
