"""Tests for chat agent factory — creation and tool structure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.chat_agent.agent import _AgentStub, create_chat_agent
from src.agents.chat_agent.deps import ChatAgentDeps


EXPECTED_TOOL_NAMES = {
    "dispatch_capability",
    "query_run_progress",
    "cancel_run",
    "write_decision",
    "read_decisions",
    "read_memory",
    "read_run_history",
    "read_documents_meta",
    "read_library_meta",
}


@pytest.fixture
def deps():
    """Minimal deps with no langchain_chat_model (stub mode)."""
    # Use plain MagicMock (no spec) so attribute assignment works freely.
    d = MagicMock()
    d.workspace_id = "ws-1"
    d.workspace_type = "thesis"
    d.user_id = "u-1"
    d.langchain_chat_model = None  # stub mode — no real LLM

    d.execution_service.list_executions = AsyncMock(return_value=[])
    d.execution_service.create_execution = AsyncMock(return_value=MagicMock(id="e-1"))
    d.execution_service.get_by_id = AsyncMock(return_value=None)
    d.execution_service.get_execution_graph = AsyncMock(return_value={})
    d.execution_service.cancel_execution = AsyncMock(return_value=None)
    d.capability_resolver.resolve = AsyncMock(return_value=MagicMock())
    d.decisions_service.get_active = AsyncMock(return_value={})
    d.decisions_service.set = AsyncMock(return_value=MagicMock(id="d-1"))
    d.memory_service.top = AsyncMock(return_value=[])
    d.run_history_service.list = AsyncMock(return_value=[])
    d.documents_service.list = AsyncMock(return_value=[])
    d.library_service.list = AsyncMock(return_value=[])
    return d


class TestCreateChatAgentStub:
    """With no langchain_chat_model, factory returns _AgentStub."""

    def test_returns_agent_stub(self, deps):
        agent = create_chat_agent(deps)
        assert isinstance(agent, _AgentStub)

    def test_stub_has_nine_tools(self, deps):
        agent = create_chat_agent(deps)
        assert len(agent.tools) == 9

    def test_stub_tool_names_match_spec(self, deps):
        agent = create_chat_agent(deps)
        assert set(agent.tool_names) == EXPECTED_TOOL_NAMES

    def test_stub_system_prompt_contains_workspace_type(self, deps):
        agent = create_chat_agent(deps)
        assert "thesis" in agent.system_prompt

    def test_custom_texts_injected(self, deps):
        agent = create_chat_agent(
            deps,
            capability_list_text="- deep_research",
            decisions_text="citation_style: MLA",
            memory_text="偏好中文",
        )
        assert "deep_research" in agent.system_prompt
        assert "citation_style: MLA" in agent.system_prompt
        assert "偏好中文" in agent.system_prompt

    @pytest.mark.parametrize(
        "ws_type",
        ["thesis", "sci", "proposal", "software_copyright", "patent"],
    )
    def test_all_workspace_types_succeed(self, ws_type: str):
        d = MagicMock()
        d.workspace_type = ws_type
        d.workspace_id = "ws-x"
        d.user_id = "u-x"
        d.langchain_chat_model = None
        # Set up all service mocks
        for attr in [
            "execution_service",
            "capability_resolver",
            "decisions_service",
            "memory_service",
            "run_history_service",
            "documents_service",
            "library_service",
        ]:
            svc = MagicMock()
            for method in ["list_executions", "create_execution", "get_by_id",
                           "get_execution_graph", "cancel_execution", "resolve",
                           "get_active", "set", "top", "list"]:
                setattr(svc, method, AsyncMock(return_value=MagicMock()))
            setattr(d, attr, svc)

        agent = create_chat_agent(d)
        assert isinstance(agent, _AgentStub)
        assert len(agent.tools) == 9


class TestDispatchBehaviorViaStub:
    """Validate dispatch_capability tool behavior through the stub."""

    @pytest.mark.asyncio
    async def test_dispatch_calls_create_execution(self, deps):
        """Dispatch tool calls execution_service.create_execution exactly once."""
        agent = create_chat_agent(deps)
        dispatch_tool = next(
            t for t in agent.tools if t.name == "dispatch_capability"
        )
        result = await dispatch_tool.ainvoke(
            {
                "capability_id": "deep_research",
                "brief": {"topic": "AI"},
                "raw_message": "研究 AI",
            }
        )
        assert result["status"] == "dispatched"
        deps.execution_service.create_execution.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_blocked_returns_lead_busy(self, deps):
        """When lead is busy, dispatch returns lead_busy error."""
        active = MagicMock(feature_id="outline", progress=30)
        deps.execution_service.list_executions = AsyncMock(return_value=[active])

        agent = create_chat_agent(deps)
        dispatch_tool = next(
            t for t in agent.tools if t.name == "dispatch_capability"
        )
        result = await dispatch_tool.ainvoke(
            {
                "capability_id": "deep_research",
                "brief": {},
                "raw_message": "go",
            }
        )
        assert result["error"] == "lead_busy"
