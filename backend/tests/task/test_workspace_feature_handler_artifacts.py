"""Artifact draft mapping tests for workspace feature LangGraph outputs."""

from src.artifacts.types import ArtifactType
from src.task.handlers.workspace_feature_handler import _build_langgraph_artifact_drafts


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
        "generation_mode": "template_fallback",
        "model_id": "deepseek-v3.2",
        "schema_version": "v1",
    }

    drafts = _build_langgraph_artifact_drafts(
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
        "generation_mode": "template_fallback",
        "model_id": "deepseek-v3.2",
    }

    drafts = _build_langgraph_artifact_drafts(
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
    drafts = _build_langgraph_artifact_drafts(
        feature_id="thesis_writing",
        workspace_name="我的课题",
        workspace_type="thesis",
        result={"action": "review_section", "review": {"overall_score": 8}},
    )

    assert drafts == []
