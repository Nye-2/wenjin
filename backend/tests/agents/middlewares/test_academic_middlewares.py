"""Tests for adapted academic middlewares working with dict-based state."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.middlewares.citation_context import CitationContextMiddleware
from src.agents.middlewares.discipline_context import DisciplineContextMiddleware
from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware


class TestWorkspaceContextWithDictState:
    @pytest.mark.asyncio
    async def test_loads_workspace_into_dict_state(self):
        mock_service = AsyncMock()
        mock_workspace = MagicMock()
        mock_workspace.type = "sci"
        mock_workspace.discipline = "computer_science"
        mock_workspace.config = {"paper_type": "sci"}
        mock_service.get.return_value = mock_workspace
        template_service = AsyncMock()
        template_service.get_active.return_value = None
        mw = WorkspaceContextMiddleware(
            mock_service,
            template_service=template_service,
        )
        state = {"messages": [], "workspace_id": "ws-123", "workspace_config": None}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert isinstance(result, dict)
        assert result.get("workspace_config") is not None


class TestDisciplineContextWithDictState:
    @pytest.mark.asyncio
    async def test_injects_norms_into_dict_state(self):
        mw = DisciplineContextMiddleware()
        state = {"messages": [], "discipline": "computer_science", "workspace_type": "sci", "discipline_norms": None}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert isinstance(result, dict)
        assert result.get("discipline_norms") is not None


class TestCitationContextWithDictState:
    @pytest.mark.asyncio
    async def test_extracts_citations_after_model(self):
        from langchain_core.messages import AIMessage
        mock_service = AsyncMock()
        mock_service.search_in_workspace.return_value = []
        mw = CitationContextMiddleware(mock_service)
        state = {
            "messages": [AIMessage(content="According to (Smith, 2023), LLMs are powerful.")],
            "workspace_id": "ws-123",
            "cited_papers": [],
        }
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert isinstance(result, dict)
