"""Unit tests for ReactSubagent — helper functions + mock-LLM integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.v2.base import SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.react import (
    ReactSubagent,
    _parse_output,
    _render_user_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(*, inputs: dict | None = None, skill=None, tools=None) -> SubagentContext:
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs or {},
        tools=tools or [],
        workspace_data={},
        skill=skill,
    )


def _make_skill(
    prompt: str = "",
    config: dict | None = None,
    resources: list | None = None,
    allowed_tools: list | None = None,
) -> MagicMock:
    skill = MagicMock()
    skill.prompt = prompt
    skill.config = config or {}
    skill.resources = resources or []
    skill.allowed_tools = allowed_tools or []
    return skill


# ---------------------------------------------------------------------------
# _render_user_message
# ---------------------------------------------------------------------------


class TestRenderUserMessage:
    def test_no_template_dumps_inputs(self):
        result = _render_user_message(None, {"topic": "AI", "n": 5})
        parsed = json.loads(result)
        assert parsed == {"topic": "AI", "n": 5}

    def test_custom_template_substitution(self):
        template = "主题: {{topic}}, 数量: {{n}}"
        result = _render_user_message(template, {"topic": "量子计算", "n": 10})
        assert result == "主题: 量子计算, 数量: 10"

    def test_missing_key_replaced_with_empty(self):
        template = "Hello {{name}}, {{missing}}"
        result = _render_user_message(template, {"name": "World"})
        assert result == "Hello World, "

    def test_empty_inputs_with_template(self):
        template = "Query: {{query}}"
        result = _render_user_message(template, {})
        assert result == "Query: "

    def test_empty_inputs_no_template(self):
        result = _render_user_message(None, {})
        assert json.loads(result) == {}


# ---------------------------------------------------------------------------
# _parse_output
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_document_kind(self):
        result = _parse_output("# Title\nBody", {"output_kind": "document"})
        assert result == {"markdown": "# Title\nBody"}

    def test_json_kind_valid(self):
        payload = {"sections": ["intro", "methods"]}
        text = json.dumps(payload, ensure_ascii=False)
        result = _parse_output(text, {"output_kind": "json"})
        assert result == payload

    def test_json_kind_invalid_fallback(self):
        result = _parse_output("not valid json", {"output_kind": "json"})
        assert result == {"text": "not valid json"}

    def test_json_kind_non_dict_fallback(self):
        result = _parse_output("[1, 2, 3]", {"output_kind": "json"})
        assert result == {"text": "[1, 2, 3]"}

    def test_text_default(self):
        result = _parse_output("just some text", {"output_kind": "text"})
        assert result == {"text": "just some text"}

    def test_unknown_kind_falls_back_to_text(self):
        result = _parse_output("mystery output", {"output_kind": "unknown"})
        assert result == {"text": "mystery output"}

    def test_no_output_kind_key(self):
        result = _parse_output("plain output", {})
        assert result == {"text": "plain output"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_registered_in_global_registry(self):
        assert "react" in REGISTRY.all_names()
        assert REGISTRY.get("react") is ReactSubagent


# ---------------------------------------------------------------------------
# No skill => empty output
# ---------------------------------------------------------------------------


class TestNoSkill:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skill(self):
        sub = ReactSubagent()
        ctx = _make_ctx(skill=None)
        result = await sub.run(ctx)
        assert result.output == {"text": ""}


# ---------------------------------------------------------------------------
# Task 13: Mock LLM integration test
# ---------------------------------------------------------------------------


class TestMockLLM:
    @pytest.mark.asyncio
    async def test_skill_with_mock_model(self):
        """Verify ReactSubagent calls the model via astream and parses document output."""
        # Build fake stream chunks (LangChain AIMessageChunk-like)
        fake_chunk = MagicMock()
        fake_chunk.content = "# 综述报告\n\n这是一篇关于量子计算的综述。"
        fake_chunk.additional_kwargs = {}

        async def _fake_astream(messages):
            yield fake_chunk

        fake_model = MagicMock()
        fake_model.astream = MagicMock(return_value=_fake_astream([]))

        with patch(
            "src.subagents.v2.types.react.create_chat_model",
            return_value=fake_model,
        ):
            sub = ReactSubagent()
            skill = _make_skill(
                prompt="你是综述写手",
                config={
                    "output_kind": "document",
                    "user_template": "主题: {{topic}}",
                },
            )
            ctx = _make_ctx(inputs={"topic": "量子计算"}, skill=skill)
            result = await sub.run(ctx)

        # Verify model.astream was called with system + user messages
        fake_model.astream.assert_called_once()
        call_args = fake_model.astream.call_args[0][0]  # positional arg: messages list
        assert len(call_args) == 2
        assert call_args[0].content == "你是综述写手"
        assert call_args[1].content == "主题: 量子计算"

        # Verify output parsed as document
        assert result.output == {
            "markdown": "# 综述报告\n\n这是一篇关于量子计算的综述。"
        }
