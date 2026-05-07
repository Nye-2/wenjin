"""Spec §1.1 — these tokens MUST NOT appear in agent output."""
import pytest

from src.agents.lead_agent.blocks import AgentMessage, TextBlock
from src.agents.lead_agent.prompts.jargon import (
    BLACKLIST,
    assert_no_jargon,
)


def test_blacklist_contains_known_leaks():
    assert "message_feature_proposal" in BLACKLIST
    assert "意图置信度" in BLACKLIST
    assert "我会先复用" in BLACKLIST
    assert "将进入" in BLACKLIST
    assert "识别依据" in BLACKLIST


def test_clean_message_passes():
    msg = AgentMessage(blocks=[TextBlock(content="好，我先去扫文献")])
    assert_no_jargon(msg)  # no exception


def test_jargon_in_text_block_raises():
    msg = AgentMessage(blocks=[
        TextBlock(content="将进入「论文分析」执行链路。识别依据：message_feature_proposal")
    ])
    with pytest.raises(AssertionError, match="message_feature_proposal"):
        assert_no_jargon(msg)
