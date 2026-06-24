"""Schema validation for AgentBlock protocol (spec §5.1)."""
import pytest
from pydantic import ValidationError

from src.agents.chat_agent.blocks import (
    AgentMessage,
    QuestionCardBlock,
    ResultCardBlock,
    StatusLineBlock,
    TextBlock,
    ThinkingBlock,
    ToolInvocationBlock,
    ToolResultBlock,
)


def test_text_block_minimal():
    b = TextBlock(content="hello")
    assert b.kind == "text"


def test_status_line_default_tone_is_info():
    b = StatusLineBlock(label="phase 1 done", run_id="r1")
    assert b.tone == "info"


def test_status_line_rejects_unknown_tone():
    with pytest.raises(ValidationError):
        StatusLineBlock(label="x", run_id="r1", tone="boom")


def test_question_card_max_three_pills():
    with pytest.raises(ValidationError):
        QuestionCardBlock(
            label="?",
            question="why",
            pills=[{"label": str(i), "intent": str(i)} for i in range(4)],
        )


def test_result_card_requires_feedback_and_stats():
    with pytest.raises(ValidationError):
        ResultCardBlock(
            run_id="r1",
            title="t",
            tldr="x",
            findings=[{"id": "1", "text": "a"}],
        )


def test_agent_message_discriminated_union_roundtrip():
    raw = {
        "blocks": [
            {"kind": "text", "content": "hi"},
            {"kind": "thinking", "text": "checking"},
            {
                "kind": "status_line",
                "label": "phase 1 done",
                "run_id": "r1",
                "tone": "info",
            },
            {
                "kind": "tool_invocation",
                "tool": "launch_feature",
                "input": {"feature_id": "outline"},
                "tool_call_id": "call-1",
            },
            {
                "kind": "tool_result",
                "tool": "launch_feature",
                "status": "launched",
                "output": {"execution_id": "exec-1", "feature_id": "outline"},
                "execution_id": "exec-1",
                "feature_id": "outline",
                "tool_call_id": "call-1",
            },
        ]
    }
    parsed = AgentMessage.model_validate(raw)
    assert len(parsed.blocks) == 5
    assert parsed.blocks[0].kind == "text"
    assert parsed.blocks[1].kind == "thinking"
    assert parsed.blocks[2].kind == "status_line"
    assert parsed.blocks[3].kind == "tool_invocation"
    assert parsed.blocks[4].kind == "tool_result"
    # roundtrip
    assert parsed.model_dump()["blocks"] == raw["blocks"]


def test_thinking_block_minimal():
    b = ThinkingBlock(text="step 1")
    assert b.kind == "thinking"


def test_tool_invocation_uses_top_level_input():
    b = ToolInvocationBlock(
        tool="launch_feature",
        input={"feature_id": "outline"},
        tool_call_id="call-1",
    )
    assert b.model_dump(exclude_none=True) == {
        "kind": "tool_invocation",
        "tool": "launch_feature",
        "input": {"feature_id": "outline"},
        "tool_call_id": "call-1",
    }


def test_tool_result_uses_top_level_output_and_refs():
    b = ToolResultBlock(
        tool="launch_feature",
        status="launched",
        output={"execution_id": "exec-1", "feature_id": "outline"},
        execution_id="exec-1",
        feature_id="outline",
        tool_call_id="call-1",
    )
    assert b.model_dump(exclude_none=True) == {
        "kind": "tool_result",
        "tool": "launch_feature",
        "status": "launched",
        "output": {"execution_id": "exec-1", "feature_id": "outline"},
        "tool_call_id": "call-1",
        "execution_id": "exec-1",
        "feature_id": "outline",
    }
