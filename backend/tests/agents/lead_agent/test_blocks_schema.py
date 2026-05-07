"""Schema validation for AgentBlock protocol (spec §5.1)."""
import pytest
from pydantic import ValidationError

from src.agents.lead_agent.blocks import (
    AgentMessage,
    QuestionCardBlock,
    ResultCardBlock,
    StatusLineBlock,
    TextBlock,
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
            {
                "kind": "status_line",
                "label": "phase 1 done",
                "run_id": "r1",
                "tone": "info",
            },
        ]
    }
    parsed = AgentMessage.model_validate(raw)
    assert len(parsed.blocks) == 2
    assert parsed.blocks[0].kind == "text"
    assert parsed.blocks[1].kind == "status_line"
    # roundtrip
    assert parsed.model_dump()["blocks"] == raw["blocks"]
