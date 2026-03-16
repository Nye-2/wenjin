"""Thesis writing service – structured payload builders for outline and chapter.

Provides schema-versioned, deterministic payloads that the workspace_feature_handler
persists as artifacts.  The ``generation_mode`` field distinguishes LLM-produced
content from template fallback so the frontend can surface upgrade hints.
"""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_outline(raw_outline: dict[str, Any]) -> dict[str, Any]:
    """Ensure outline payload matches the frontend contract."""
    chapters = raw_outline.get("chapters")
    normalized_chapters: list[dict[str, Any]] = []
    if isinstance(chapters, list):
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            normalized_chapters.append(
                {
                    "title": str(chapter.get("title") or f"第{index}章"),
                    "position": str(chapter.get("position") or "正文"),
                    "targetWords": _safe_int(chapter.get("targetWords"), 2500),
                    "keyPoints": (
                        chapter.get("keyPoints")
                        if isinstance(chapter.get("keyPoints"), list)
                        else []
                    ),
                    "sections": (
                        chapter.get("sections")
                        if isinstance(chapter.get("sections"), list)
                        else []
                    ),
                }
            )

    return {
        "abstract": str(raw_outline.get("abstract") or ""),
        "keywords": (
            raw_outline.get("keywords")
            if isinstance(raw_outline.get("keywords"), list)
            else []
        ),
        "chapters": normalized_chapters,
    }


def _build_template_outline(paper_title: str, target_words: int) -> dict[str, Any]:
    """Build a deterministic minimal outline (template fallback)."""
    chapter_targets = [0.12, 0.2, 0.24, 0.24, 0.2]
    chapter_titles = [
        "绪论",
        "相关工作与理论基础",
        "方法与系统设计",
        "实验与结果分析",
        "结论与展望",
    ]
    chapter_positions = [
        "研究背景与问题定义",
        "文献梳理与理论框架",
        "核心方法与实现细节",
        "实验设置、结果与讨论",
        "研究结论、局限与未来工作",
    ]

    chapters = []
    for idx, (ratio, title, position) in enumerate(
        zip(chapter_targets, chapter_titles, chapter_positions, strict=True)
    ):
        chapter_words = max(1000, int(target_words * ratio))
        chapters.append(
            {
                "title": title,
                "position": position,
                "targetWords": chapter_words,
                "keyPoints": [
                    f"{paper_title}在{title}中的核心论点",
                    "本章与全文主线的衔接关系",
                ],
                "sections": [
                    f"{idx + 1}.1 研究问题与目标",
                    f"{idx + 1}.2 方法或论证展开",
                    f"{idx + 1}.3 小结",
                ],
            }
        )

    return _normalize_outline(
        {
            "abstract": f"本文围绕《{paper_title}》展开研究，提出可执行的技术路线并验证其有效性。",
            "keywords": ["研究方法", "系统实现", "实验分析"],
            "chapters": chapters,
        }
    )


def build_outline_payload(
    *,
    paper_title: str,
    target_words: int = 20000,
    literature_count: int = 0,
    deep_research_artifact_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a v1-schema outline payload.

    Currently uses template fallback; LLM path can be wired later without
    changing the caller contract.
    """
    outline = _build_template_outline(paper_title, target_words)
    return {
        "paper_title": paper_title,
        "outline": outline,
        "generation_mode": "template_fallback",
        "source_context": {
            "literature_count": literature_count,
            "deep_research_artifact_ids": deep_research_artifact_ids or [],
        },
        "schema_version": "v1",
    }


def build_chapter_payload(
    *,
    paper_title: str,
    chapter_index: int,
    chapter_title: str,
    target_words: int = 2500,
    references_used: list[str] | None = None,
) -> dict[str, Any]:
    """Build a v1-schema chapter payload.

    Currently uses template fallback; LLM path can be wired later without
    changing the caller contract.
    """
    chapter_markdown = "\n\n".join(
        [
            f"# {chapter_title}",
            f"## 研究背景\n围绕《{paper_title}》展开本章论证，明确研究场景与问题边界。",
            "## 核心内容\n给出关键方法、实验设计或理论推导，并说明实现路径。",
            "## 本章小结\n总结本章结论并衔接后续章节。",
        ]
    )
    estimated_words = max(800, int(target_words * 0.35))

    return {
        "paper_title": paper_title,
        "chapter_index": chapter_index,
        "chapter_title": chapter_title,
        "target_words": target_words,
        "estimated_words": estimated_words,
        "markdown": chapter_markdown,
        "references_used": references_used or [],
        "generation_mode": "template_fallback",
        "schema_version": "v1",
    }
