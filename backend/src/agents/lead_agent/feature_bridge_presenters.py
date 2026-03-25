"""Presentation helpers for workspace feature bridge cards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.workspace_features import iter_workspace_features

_FEATURE_TITLE_OVERRIDES: dict[str, str] = {
    "writing": "SCI 写作",
    "framework_outline": "论文框架与摘要",
    "copyright_materials": "软著材料清单",
    "technical_description": "技术说明书",
}

_FEATURE_TITLES: dict[str, str] = {
    feature.id: feature.name
    for feature in iter_workspace_features()
}
_FEATURE_TITLES.update(_FEATURE_TITLE_OVERRIDES)


def feature_title(feature_id: str) -> str:
    """Resolve a human-friendly feature title."""
    return _FEATURE_TITLES.get(feature_id, feature_id)


def _artifact_summary(artifacts: list[dict[str, Any]]) -> str | None:
    if not artifacts:
        return None
    if len(artifacts) == 1:
        title = str(artifacts[0].get("title") or "").strip()
        if title:
            return f"已生成 artifact「{title}」"
        return "已生成 1 个 artifact"
    return f"已生成 {len(artifacts)} 个 artifacts"


def summarize_feature_result(
    feature_id: str,
    data: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
) -> str:
    """Build a compact completion summary for a feature task."""
    artifact_text = _artifact_summary(artifacts)

    if feature_id == "literature_search":
        top_hits = data.get("top_hits")
        hits_count = len(top_hits) if isinstance(top_hits, list) else 0
        parts = [f"已完成文献检索，整理出 {hits_count} 条高相关候选。"] if hits_count else ["已完成文献检索。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "literature_management":
        summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
        total = summary.get("total") if isinstance(summary, Mapping) else 0
        core_count = summary.get("core_count") if isinstance(summary, Mapping) else 0
        parts = [
            f"文献管理已完成，当前共盘点 {total or 0} 篇文献，其中核心文献 {core_count or 0} 篇。"
        ]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "paper_analysis":
        sections = data.get("sections")
        section_count = len(sections) if isinstance(sections, Mapping) else 0
        recommendations = data.get("recommendations")
        recommendation_count = len(recommendations) if isinstance(recommendations, list) else 0
        parts = [
            f"论文分析已完成，整理出 {section_count or 0} 个分析分区和 {recommendation_count or 0} 条建议。"
        ]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "writing":
        section_title = str(
            data.get("section_title") or data.get("section_type") or "章节草稿"
        ).strip()
        word_count = data.get("word_count")
        parts = [f"已完成 {section_title} 草稿生成。"]
        if isinstance(word_count, int) and word_count > 0:
            parts.append(f"当前约 {word_count} 字。")
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id in {
        "literature_review",
        "opening_research",
        "background_research",
        "proposal_outline",
    }:
        sections = data.get("sections")
        sections_count = len(sections) if isinstance(sections, list) else 0
        parts = (
            [f"已完成结构化报告输出，包含 {sections_count} 个核心章节。"]
            if sections_count
            else [f"{feature_title(feature_id)} 已完成。"]
        )
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "framework_outline":
        sections = data.get("sections")
        section_count = len(sections) if isinstance(sections, list) else 0
        keywords = data.get("keywords")
        keyword_count = len(keywords) if isinstance(keywords, list) else 0
        parts = []
        if section_count or keyword_count:
            parts.append(
                f"已生成论文框架，包含 {section_count or '若干'} 个章节与 {keyword_count or '若干'} 个关键词。"
            )
        else:
            parts.append("已生成论文框架与摘要草案。")
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "thesis_writing":
        action = str(data.get("action") or "").strip().lower()
        if action == "generate_outline":
            outline = data.get("outline")
            chapters = outline.get("chapters") if isinstance(outline, Mapping) else []
            chapter_count = len(chapters) if isinstance(chapters, list) else 0
            parts = (
                [f"论文大纲已生成，当前包含 {chapter_count} 个章节。"]
                if chapter_count
                else ["论文大纲已生成。"]
            )
        elif action == "write_chapter":
            chapter = data.get("chapter") if isinstance(data.get("chapter"), Mapping) else {}
            chapter_title = str(
                chapter.get("chapter_title") or chapter.get("title") or "章节草稿"
            ).strip()
            parts = [f"已完成《{chapter_title}》章节写作。"]
        elif action == "write_all":
            chapters = data.get("chapters")
            chapter_count = len(chapters) if isinstance(chapters, list) else 0
            parts = (
                [f"全文写作已完成，当前整理出 {chapter_count} 个章节草稿。"]
                if chapter_count
                else ["全文写作已完成。"]
            )
        else:
            parts = [f"{feature_title(feature_id)} 已完成。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "peer_review":
        weaknesses = data.get("weaknesses")
        weakness_count = len(weaknesses) if isinstance(weaknesses, list) else 0
        parts = (
            [f"已完成同行评审，识别出 {weakness_count} 个主要问题。"]
            if weakness_count
            else ["已完成同行评审。"]
        )
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "journal_recommend":
        journals = data.get("journals")
        journal_count = len(journals) if isinstance(journals, list) else 0
        parts = (
            [f"已完成期刊推荐，给出 {journal_count} 个候选期刊。"]
            if journal_count
            else ["已完成期刊推荐。"]
        )
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "experiment_design":
        variables = data.get("variables")
        variable_count = len(variables) if isinstance(variables, list) else 0
        parts = (
            [f"实验设计已完成，整理出 {variable_count} 组关键变量。"]
            if variable_count
            else ["实验设计已完成。"]
        )
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "copyright_materials":
        required_materials = data.get("required_materials")
        review_checklist = data.get("review_checklist")
        materials_count = len(required_materials) if isinstance(required_materials, list) else 0
        checklist_count = len(review_checklist) if isinstance(review_checklist, list) else 0
        parts = [
            f"软著材料清单已生成，包含 {materials_count} 项材料和 {checklist_count} 条核对项。"
        ]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "technical_description":
        sections = data.get("sections")
        section_count = len(sections) if isinstance(sections, Mapping) else 0
        parts = [f"技术说明书已生成，当前包含 {section_count or 0} 个核心章节。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "patent_outline":
        sections = data.get("sections")
        section_count = len(sections) if isinstance(sections, list) else 0
        claims_draft = data.get("claims_draft")
        independent_claims = (
            claims_draft.get("independent_claims")
            if isinstance(claims_draft, Mapping)
            else []
        )
        claim_count = len(independent_claims) if isinstance(independent_claims, list) else 0
        parts = [f"专利框架已生成，包含 {section_count or 0} 个章节和 {claim_count or 0} 条独立权利要求。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "prior_art_search":
        comparison_table = data.get("comparison_table")
        novelty_risks = data.get("novelty_risks")
        comparison_count = len(comparison_table) if isinstance(comparison_table, list) else 0
        risk_count = len(novelty_risks) if isinstance(novelty_risks, list) else 0
        parts = [f"现有技术检索已完成，整理出 {comparison_count or 0} 条对比项和 {risk_count or 0} 个风险点。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "figure_generation":
        description = str(data.get("description") or "").strip()
        parts = [f"图表已生成：{description}。"] if description else ["图表生成已完成。"]
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "compile_export":
        compile_status = str(data.get("compile_status") or "").strip()
        page_count = data.get("page_count")
        parts = ["编译导出已完成。"]
        if compile_status:
            parts.append(f"当前状态：{compile_status}。")
        if page_count is not None:
            parts.append(f"页数：{page_count}。")
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    if feature_id == "deep_research":
        ideas = data.get("ideas")
        gaps = data.get("gaps")
        idea_count = len(ideas) if isinstance(ideas, list) else 0
        gap_count = len(gaps) if isinstance(gaps, list) else 0
        parts = []
        if idea_count or gap_count:
            parts.append(
                f"深度调研已完成，整理出 {idea_count} 个研究创意与 {gap_count} 个研究空白。"
            )
        else:
            parts.append("深度调研已完成。")
        if artifact_text:
            parts.append(artifact_text)
        return " ".join(parts)

    parts = [f"{feature_title(feature_id)} 已完成。"]
    if artifact_text:
        parts.append(artifact_text)
    return " ".join(parts)
