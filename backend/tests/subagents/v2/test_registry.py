"""Tests for the subagent v2 registry."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentBase, SubagentContext, SubagentResult, subagent


# ---------------------------------------------------------------------------
# Helpers — test subagent implementations isolated to this module
# ---------------------------------------------------------------------------


def _make_test_subagent(agent_name: str) -> type[SubagentBase]:
    """Dynamically create a minimal subagent class and register it."""

    @subagent(agent_name)
    class _TestAgent(SubagentBase):
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            return SubagentResult(output={"ok": True})

    return _TestAgent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_retrieve(self):
        """@subagent decorator registers and REGISTRY.get returns the class."""
        cls = _make_test_subagent("_test_reg_retrieve")
        retrieved = REGISTRY.get("_test_reg_retrieve")
        assert retrieved is cls

    def test_unknown_subagent_raises(self):
        """REGISTRY.get for an unregistered name raises KeyError."""
        with pytest.raises(KeyError, match="not registered"):
            REGISTRY.get("__does_not_exist__")

    def test_register_sets_name_attr(self):
        """After registration, the class's .name attribute equals the registered name."""
        _make_test_subagent("_test_name_attr")
        cls = REGISTRY.get("_test_name_attr")
        assert cls.name == "_test_name_attr"

    def test_all_names_lists_registered(self):
        """all_names() returns a list that includes all registered subagent names."""
        _make_test_subagent("_test_all_a")
        _make_test_subagent("_test_all_b")
        names = REGISTRY.all_names()
        assert "_test_all_a" in names
        assert "_test_all_b" in names

    def test_register_overwrite(self):
        """Re-registering the same name replaces the previous class."""

        @subagent("_test_overwrite")
        class AgentV1(SubagentBase):
            async def run(self, ctx):
                return SubagentResult(output={"version": 1})

        @subagent("_test_overwrite")
        class AgentV2(SubagentBase):
            async def run(self, ctx):
                return SubagentResult(output={"version": 2})

        assert REGISTRY.get("_test_overwrite") is AgentV2

    def test_all_names_returns_list(self):
        """all_names() always returns a plain list."""
        result = REGISTRY.all_names()
        assert isinstance(result, list)

    async def test_registered_subagent_is_runnable(self):
        """A registered subagent can be instantiated and awaited."""
        _make_test_subagent("_test_runnable")
        cls = REGISTRY.get("_test_runnable")
        instance = cls()
        ctx = SubagentContext(
            workspace_id="ws-1",
            execution_id="exec-1",
            prompt="test",
            inputs={},
            tools=[],
        )
        result = await instance.run(ctx)
        assert result.output == {"ok": True}
