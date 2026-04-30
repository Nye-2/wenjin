"""Artifact draft mapping tests for workspace feature LangGraph outputs."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.artifacts.types import ArtifactType
from src.task.workspace_feature_artifacts import build_langgraph_artifact_drafts
from src.workspace_features import iter_workspace_features

ARTIFACT_COVERAGE_MATRIX: list[tuple[str, str, str, dict[str, object], str]] = [
    (
        "thesis",
        "deep_research",
        ArtifactType.DEEP_RESEARCH_REPORT.value,
        {"topic": "研究主题", "ideas": [], "gaps": [], "schema_version": "v1"},
        "深度调研报告",
    ),
    (
        "thesis",
        "literature_management",
        ArtifactType.LITERATURE_INVENTORY.value,
        {"items": []},
        "文献管理盘点",
    ),
    (
        "thesis",
        "opening_research",
        ArtifactType.OPENING_REPORT.value,
        {"report_type": ArtifactType.OPENING_REPORT.value, "summary": "开题摘要"},
        "开题报告",
    ),
    (
        "thesis",
        "thesis_writing",
        ArtifactType.FRAMEWORK_OUTLINE.value,
        {
            "action": "generate_outline",
            "paper_title": "测试论文",
            "outline": {"chapters": [{"title": "绪论"}]},
        },
        "论文大纲",
    ),
    (
        "thesis",
        "figure_generation",
        ArtifactType.FIGURE.value,
        {"description": "系统架构图"},
        "系统架构图",
    ),
    (
        "sci",
        "literature_search",
        ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        {"query": "LLM planning"},
        "Literature Search",
    ),
    (
        "sci",
        "paper_analysis",
        ArtifactType.PAPER_ANALYSIS.value,
        {"paper_title": "Paper A"},
        "Paper Analysis",
    ),
    (
        "sci",
        "writing",
        ArtifactType.PAPER_DRAFT.value,
        {
            "section_type": "introduction",
            "section_title": "Introduction",
            "content": "Draft",
        },
        "Introduction",
    ),
    (
        "sci",
        "literature_review",
        ArtifactType.LITERATURE_REVIEW.value,
        {"summary": "Review"},
        "Literature Review",
    ),
    (
        "sci",
        "framework_outline",
        ArtifactType.FRAMEWORK_OUTLINE.value,
        {"paper_title": "Paper A", "sections": []},
        "Framework Outline",
    ),
    (
        "sci",
        "peer_review",
        ArtifactType.REVIEW.value,
        {"overall_assessment": "Strong draft"},
        "Peer Review",
    ),
    (
        "sci",
        "journal_recommend",
        ArtifactType.SUMMARY.value,
        {"journals": []},
        "Journal Recommendations",
    ),
    (
        "proposal",
        "proposal_outline",
        ArtifactType.PROPOSAL.value,
        {"sections": []},
        "申报书大纲",
    ),
    (
        "proposal",
        "background_research",
        ArtifactType.BACKGROUND_RESEARCH.value,
        {"sections": []},
        "背景调研报告",
    ),
    (
        "proposal",
        "experiment_design",
        ArtifactType.METHODOLOGY.value,
        {"variables": []},
        "实验设计",
    ),
    (
        "software_copyright",
        "copyright_materials",
        ArtifactType.COPYRIGHT_MATERIALS.value,
        {"software_profile": {"software_name": "Agent Studio"}},
        "软著申请材料清单",
    ),
    (
        "software_copyright",
        "technical_description",
        ArtifactType.TECHNICAL_DESCRIPTION.value,
        {"sections": {}},
        "技术说明书",
    ),
    (
        "patent",
        "patent_outline",
        ArtifactType.PATENT_OUTLINE.value,
        {"sections": []},
        "专利说明书框架",
    ),
    (
        "patent",
        "prior_art_search",
        ArtifactType.PRIOR_ART_REPORT.value,
        {"comparison_table": []},
        "现有技术分析",
    ),
]


def test_artifact_coverage_matrix_matches_registry() -> None:
    declared_feature_ids = {feature.id for feature in iter_workspace_features()}
    covered_feature_ids = {feature_id for _, feature_id, _, _, _ in ARTIFACT_COVERAGE_MATRIX}

    assert covered_feature_ids == declared_feature_ids


@pytest.mark.parametrize(
    ("workspace_type", "feature_id", "expected_type", "result", "title_fragment"),
    ARTIFACT_COVERAGE_MATRIX,
)
def test_all_workspace_features_produce_expected_artifact_drafts(
    workspace_type: str,
    feature_id: str,
    expected_type: str,
    result: dict[str, object],
    title_fragment: str,
) -> None:
    drafts = build_langgraph_artifact_drafts(
        feature_id=feature_id,
        workspace_name="Workspace Alpha",
        workspace_type=workspace_type,
        result=deepcopy(result),
    )

    assert len(drafts) == 1
    assert drafts[0]["type"] == expected_type
    assert title_fragment in str(drafts[0]["title"])


def test_thesis_writing_generate_outline_maps_to_framework_outline() -> None:
    result = {
        "action": "generate_outline",
        "paper_title": "测试论文",
        "outline": {
            "abstract": "摘要",
            "keywords": ["方法"],
            "chapters": [
                {
                    "title": "绪论",
                    "position": "背景",
                    "targetWords": 1800,
                    "keyPoints": ["问题定义"],
                    "sections": ["1.1 背景"],
                }
            ],
        },
        "source_context": {"literature_count": 8},
        "generation_mode": "llm",
        "model_id": "deepseek-v3.2",
        "schema_version": "v1",
    }

    drafts = build_langgraph_artifact_drafts(
        feature_id="thesis_writing",
        workspace_name="我的课题",
        workspace_type="thesis",
        result=result,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["type"] == ArtifactType.FRAMEWORK_OUTLINE.value
    assert draft["title"] == "我的课题 - 论文大纲"
    assert draft["content"]["paper_title"] == "测试论文"
    assert draft["content"]["outline"]["chapters"][0]["title"] == "绪论"


def test_thesis_writing_write_chapter_maps_to_thesis_chapter() -> None:
    result = {
        "action": "write_chapter",
        "chapter": {
            "paper_title": "测试论文",
            "chapter_index": 0,
            "chapter_title": "绪论",
            "target_words": 2500,
            "estimated_words": 900,
            "markdown": "# 绪论\n\n正文",
            "references_used": ["ref-1"],
            "schema_version": "v1",
        },
        "generation_mode": "llm",
        "model_id": "deepseek-v3.2",
    }

    drafts = build_langgraph_artifact_drafts(
        feature_id="thesis_writing",
        workspace_name="我的课题",
        workspace_type="thesis",
        result=result,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["type"] == ArtifactType.THESIS_CHAPTER.value
    assert draft["title"] == "我的课题 - 绪论"
    assert draft["content"]["chapter_index"] == 0
    assert draft["content"]["chapter_title"] == "绪论"
    assert draft["content"]["model_id"] == "deepseek-v3.2"


def test_thesis_writing_unknown_action_does_not_create_draft() -> None:
    drafts = build_langgraph_artifact_drafts(
        feature_id="thesis_writing",
        workspace_name="我的课题",
        workspace_type="thesis",
        result={"action": "review_section", "review": {"overall_score": 8}},
    )

    assert drafts == []


def test_thesis_deep_research_includes_ideas_and_gaps_in_artifact() -> None:
    result = {
        "schema_version": "v1",
        "source_feature": "deep_research",
        "topic": "测试主题",
        "discipline": "计算机科学",
        "query": {"keywords": ["测试主题"], "constraints": []},
        "source": "semantic_scholar",
        "corpus": {
            "verified_count": 2,
            "verified_papers": [
                {"title": "Seminal A", "external_id": "ss-1"},
                {"title": "Recent B", "external_id": "ss-2"},
            ],
        },
        "verified_papers": [
            {"title": "Seminal A", "external_id": "ss-1"},
            {"title": "Recent B", "external_id": "ss-2"},
        ],
        "discovery": {
            "source": "semantic_scholar",
            "verified_papers": [
                {"title": "Seminal A", "external_id": "ss-1"},
                {"title": "Recent B", "external_id": "ss-2"},
            ],
            "trends": [{"topic": "Trend C"}],
        },
        "gaps": [{"description": "数据集泛化不足"}],
        "ideas": [
            {
                "title": "跨域泛化方法",
                "description": "结合自监督与迁移学习提升泛化性能",
                "novelty_assessment": "具备方法组合创新",
            }
        ],
        "cross_validation": {"validation_score": 8},
        "model_id": "deepseek-v3.2",
        "pipeline_steps": {"discovery": True, "gap_mining": True, "synthesis": True, "cross_validation": True},
        "generation_mode": "llm",
        "generated_at": "2026-03-20T00:00:00+00:00",
    }

    drafts = build_langgraph_artifact_drafts(
        feature_id="deep_research",
        workspace_name="我的课题",
        workspace_type="thesis",
        result=result,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["type"] == ArtifactType.DEEP_RESEARCH_REPORT.value
    content = draft["content"]
    assert content["schema_version"] == "v1"
    assert content["source_feature"] == "deep_research"
    assert content["topic"] == "测试主题"
    assert content["discipline"] == "计算机科学"
    assert len(content["ideas"]) == 1
    assert len(content["gaps"]) == 1


def test_sci_framework_outline_maps_to_framework_artifact() -> None:
    drafts = build_langgraph_artifact_drafts(
        feature_id="framework_outline",
        workspace_name="SCI Topic",
        workspace_type="sci",
        result={
            "paper_title": "LLM Planning",
            "abstract": "Abstract",
            "sections": [{"title": "Introduction", "focus": "Background"}],
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["type"] == ArtifactType.FRAMEWORK_OUTLINE.value
    assert drafts[0]["title"] == "SCI Topic - Framework Outline"


def test_proposal_experiment_design_maps_to_methodology_artifact() -> None:
    drafts = build_langgraph_artifact_drafts(
        feature_id="experiment_design",
        workspace_name="Proposal Topic",
        workspace_type="proposal",
        result={
            "topic": "Agent evaluation",
            "variables": [{"name": "x", "type": "independent"}],
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["type"] == ArtifactType.METHODOLOGY.value
    assert drafts[0]["title"] == "Proposal Topic - 实验设计"


def test_sci_writing_prefers_readable_section_title_for_artifact_title() -> None:
    drafts = build_langgraph_artifact_drafts(
        feature_id="writing",
        workspace_name="SCI Topic",
        workspace_type="sci",
        result={
            "section_type": "introduction",
            "section_title": "Introduction",
            "content": "Draft body",
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["title"] == "SCI Topic - Introduction"
