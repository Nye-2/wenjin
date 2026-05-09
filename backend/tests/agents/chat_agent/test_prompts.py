"""Tests for chat agent prompts — shape + content for all 5 workspace types."""

from __future__ import annotations

import pytest

from src.agents.chat_agent.prompts import WORKSPACE_TYPES, get_system_prompt


class TestGetSystemPromptAllTypes:
    """All 5 workspace types must return a valid non-empty prompt."""

    @pytest.mark.parametrize("ws_type", sorted(WORKSPACE_TYPES))
    def test_returns_string(self, ws_type: str):
        prompt = get_system_prompt(ws_type)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    @pytest.mark.parametrize("ws_type", sorted(WORKSPACE_TYPES))
    def test_contains_workspace_type(self, ws_type: str):
        prompt = get_system_prompt(ws_type)
        assert ws_type in prompt

    @pytest.mark.parametrize("ws_type", sorted(WORKSPACE_TYPES))
    def test_no_unfilled_placeholders(self, ws_type: str):
        """Default call must not leave {placeholder} tokens."""
        prompt = get_system_prompt(ws_type)
        # If any {word} remains it was not substituted
        import re
        leftovers = re.findall(r"\{[a-z_]+\}", prompt)
        assert leftovers == [], f"Unfilled placeholders: {leftovers}"


class TestUnknownWorkspaceType:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown workspace_type"):
            get_system_prompt("unknown_type")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            get_system_prompt("")


class TestPromptSubstitutions:
    def test_capability_list_injected(self):
        prompt = get_system_prompt(
            "thesis", capability_list="- deep_research\n- outline"
        )
        assert "deep_research" in prompt

    def test_decisions_injected(self):
        prompt = get_system_prompt("thesis", decisions="citation_style: APA")
        assert "citation_style: APA" in prompt

    def test_memory_facts_injected(self):
        prompt = get_system_prompt("thesis", memory_facts="用户偏好英文输出")
        assert "用户偏好英文输出" in prompt

    def test_default_placeholders_present(self):
        """When no substitutions passed, defaults fill in."""
        prompt = get_system_prompt("sci")
        assert "(待动态注入)" in prompt
        assert "(无)" in prompt

    def test_style_guidance_thesis(self):
        prompt = get_system_prompt("thesis")
        assert "学术" in prompt or "论文" in prompt

    def test_style_guidance_patent(self):
        prompt = get_system_prompt("patent")
        assert "专利" in prompt or "权利" in prompt

    def test_style_guidance_software_copyright(self):
        prompt = get_system_prompt("software_copyright")
        assert "技术" in prompt or "架构" in prompt
