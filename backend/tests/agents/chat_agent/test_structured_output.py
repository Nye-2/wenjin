"""Spec §5.5 — LLM-JSON failure degrades to TextBlock, not raise."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.chat_agent.blocks import (
    AgentMessage,
    StatusLineBlock,
    TextBlock,
)
from src.agents.chat_agent.structured_output import parse_with_fallback


@pytest.mark.asyncio
async def test_returns_parsed_message_on_success():
    fake_llm = AsyncMock()
    structured_llm = AsyncMock()
    structured_llm.ainvoke = AsyncMock(
        return_value=AgentMessage(
            blocks=[StatusLineBlock(label="ok", run_id="r1")]
        )
    )
    fake_llm.with_structured_output = MagicMock(return_value=structured_llm)
    msg = await parse_with_fallback(fake_llm, "prompt-text", run_id="r1")
    assert msg.blocks[0].kind == "status_line"


@pytest.mark.asyncio
async def test_invalid_json_degrades_to_text_block():
    fake_llm = AsyncMock()
    # First call raises (structured), second call returns plain text
    structured_llm = AsyncMock()
    structured_llm.ainvoke = AsyncMock(
        side_effect=ValueError("invalid JSON from model")
    )
    fake_llm.with_structured_output = MagicMock(return_value=structured_llm)
    fake_llm.ainvoke = AsyncMock(return_value=type("Msg", (), {"content": "raw text"})())

    with patch("src.agents.chat_agent.structured_output.record_parse_failure") as metric:
        msg = await parse_with_fallback(fake_llm, "prompt-text", run_id="r1")

    assert isinstance(msg.blocks[0], TextBlock)
    assert msg.blocks[0].content == "prompt-text"
    metric.assert_called_once()


@pytest.mark.asyncio
async def test_dev_scripted_message_queue_is_disabled_unless_explicitly_enabled(monkeypatch):
    queued = AgentMessage(blocks=[TextBlock(content="queued-test-message")])
    real = AgentMessage(blocks=[TextBlock(content="real-model-message")])

    fake_llm = AsyncMock()
    structured_llm = AsyncMock()
    structured_llm.ainvoke = AsyncMock(return_value=real)
    fake_llm.with_structured_output = MagicMock(return_value=structured_llm)

    monkeypatch.setattr(
        "src.agents.chat_agent.structured_output.get_settings",
        lambda: SimpleNamespace(environment="development", e2e_test_hooks_enabled=False),
    )
    monkeypatch.setattr(
        "src.gateway.routers.dev_test_hooks.pop_next",
        lambda: queued,
    )

    msg = await parse_with_fallback(fake_llm, "prompt-text", run_id="r1")

    assert msg.blocks[0].content == "real-model-message"
    structured_llm.ainvoke.assert_awaited_once()
