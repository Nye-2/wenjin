from __future__ import annotations

import pytest

from src.subagents.v2.base import SubagentContext
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.prism import PrismSelectionOptimizerSubagent


@pytest.mark.asyncio
async def test_prism_selection_optimizer_returns_reviewable_file_change(monkeypatch):
    async def fake_rewrite_with_feedback(**kwargs):
        assert kwargs["comment"] == "加强贡献表述"
        assert kwargs["selected_text"] == "原始贡献"
        assert kwargs["scope"] == "selection"
        return {
            "model_id": "test-model",
            "scope": "selection",
            "resolved_selection_start": 10,
            "resolved_selection_end": 14,
            "target_start": 10,
            "target_end": 14,
            "section_title": "引言",
            "section_level": "section",
            "rewritten_text": "清晰贡献",
            "changes_summary": "强化贡献点表达",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.prism.rewrite_with_feedback",
        fake_rewrite_with_feedback,
    )
    emitted: list[tuple[str, str]] = []

    async def emit_delta(event_type: str, content: str) -> None:
        emitted.append((event_type, content))

    ctx = SubagentContext(
        workspace_id="workspace-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "file_path": "sections/intro.tex",
            "file_content": "0123456789原始贡献ABC",
            "selected_text": "原始贡献",
            "instruction": "加强贡献表述",
            "selection_start": 10,
            "selection_end": 14,
            "scope": "selection",
            "feedback_id": "fb-1",
        },
        tools=[],
        emit_delta=emit_delta,
    )

    result = await PrismSelectionOptimizerSubagent().run(ctx)

    assert result.output["path"] == "sections/intro.tex"
    assert result.output["pending_content"] == "0123456789清晰贡献ABC"
    assert result.output["content_format"] == "raw"
    assert result.output["logical_key"] == "prism_selection_optimize:fb-1"
    assert result.output["reason"] == "强化贡献点表达"
    assert result.tool_calls and result.tool_calls[0]["name"] == "prism.feedback_rewrite"
    assert any("Prism 选区" in content for _, content in emitted)


def test_prism_selection_optimizer_is_registered():
    assert REGISTRY.get("prism_selection_optimizer") is PrismSelectionOptimizerSubagent


@pytest.mark.asyncio
async def test_prism_document_rewrite_injects_bounded_workspace_context(monkeypatch):
    captured_comment = ""

    async def fake_rewrite_with_feedback(**kwargs):
        nonlocal captured_comment
        captured_comment = kwargs["comment"]
        assert kwargs["scope"] == "document"
        content_length = len(str(kwargs["content"]))
        return {
            "model_id": "test-model",
            "scope": "document",
            "resolved_selection_start": 0,
            "resolved_selection_end": content_length,
            "target_start": 0,
            "target_end": content_length,
            "section_title": "全文",
            "section_level": "document",
            "rewritten_text": "整体修改稿",
            "changes_summary": "全文降 AI 味",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.prism.rewrite_with_feedback",
        fake_rewrite_with_feedback,
    )

    async def emit_delta(_event_type: str, _content: str) -> None:
        return None

    ctx = SubagentContext(
        workspace_id="workspace-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "file_path": "main.tex",
            "file_content": "原始全文内容需要调整",
            "selected_text": "原始全文内容需要调整",
            "instruction": "这篇文章 AI 味太浓了",
            "selection_start": 0,
            "selection_end": 10,
            "scope": "document",
            "rewrite_mode": "document",
            "context_strategy": "workspace_manuscript_review",
            "context_requirements": {
                "include_workspace_history": True,
                "include_related_documents": True,
                "include_sandbox_artifacts": True,
            },
            "feedback_id": "document:job-1",
        },
        workspace_data={
            "related_documents": [
                {
                    "title": "Federated Learning with LLMs",
                    "citation_key": "fl_llm_2026",
                    "abstract_excerpt": "A survey of federated learning for large language models.",
                }
            ],
            "workspace_history": {
                "decisions": [{"key": "目标风格", "value": "降低模板化表达"}],
                "memory": [{"content": "用户偏好更像真实研究者写作。"}],
                "recent_executions": [{"display_name": "实验复核", "summary": "已有实验代码位于 sandbox。"}],
            },
            "sandbox_context": {
                "artifacts": [{"artifact_kind": "code", "path": "experiments/train.py"}],
            },
        },
        tools=[],
        emit_delta=emit_delta,
    )

    result = await PrismSelectionOptimizerSubagent().run(ctx)

    assert "这篇文章 AI 味太浓了" in captured_comment
    assert "工作区上下文" in captured_comment
    assert "Federated Learning with LLMs" in captured_comment
    assert "降低模板化表达" in captured_comment
    assert "experiments/train.py" in captured_comment
    assert result.output["rewrite_mode"] == "document"
    assert result.output["used_context"] == {
        "related_documents": 1,
        "decisions": 1,
        "memory": 1,
        "recent_executions": 1,
        "sandbox_artifacts": 1,
    }
