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
