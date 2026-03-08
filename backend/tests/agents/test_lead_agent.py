"""Tests for Lead Agent middleware chain integration."""

from unittest.mock import MagicMock

from src.agents.lead_agent.agent import (
    apply_prompt_template,
    build_middlewares,
    make_lead_agent,
)
from src.agents.middlewares import (
    CitationContextMiddleware,
    DisciplineContextMiddleware,
    KnowledgeContextMiddleware,
    LiteratureContextMiddleware,
    WorkspaceContextMiddleware,
)
from src.agents.thread_state import ThreadState


class TestBuildMiddlewares:
    """Tests for build_middlewares function."""

    def test_build_middlewares_creates_all_five(self):
        """Test that build_middlewares creates all 5 middlewares when services provided."""
        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        paper_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            paper_service=paper_service,
        )

        assert len(middlewares) == 5

    def test_build_middlewares_order_is_correct(self):
        """Test that middleware order is correct."""
        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        paper_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            paper_service=paper_service,
        )

        # Verify order:
        # 1. WorkspaceContextMiddleware
        # 2. LiteratureContextMiddleware
        # 3. KnowledgeContextMiddleware
        # 4. DisciplineContextMiddleware
        # 5. CitationContextMiddleware
        assert isinstance(middlewares[0], WorkspaceContextMiddleware)
        assert isinstance(middlewares[1], LiteratureContextMiddleware)
        assert isinstance(middlewares[2], KnowledgeContextMiddleware)
        assert isinstance(middlewares[3], DisciplineContextMiddleware)
        assert isinstance(middlewares[4], CitationContextMiddleware)

    def test_build_middlewares_only_with_services(self):
        """Test that middlewares are only created when services are provided."""
        # No services
        middlewares = build_middlewares()
        # DisciplineContextMiddleware is always created (no service required)
        assert len(middlewares) == 1
        assert isinstance(middlewares[0], DisciplineContextMiddleware)

    def test_build_middlewares_partial_services(self):
        """Test that middlewares are created for provided services only."""
        workspace_service = MagicMock()

        middlewares = build_middlewares(workspace_service=workspace_service)

        # Should have WorkspaceContextMiddleware and DisciplineContextMiddleware
        assert len(middlewares) == 2
        assert isinstance(middlewares[0], WorkspaceContextMiddleware)
        assert isinstance(middlewares[1], DisciplineContextMiddleware)


class TestApplyPromptTemplate:
    """Tests for apply_prompt_template function."""

    def test_prompt_includes_literature_context(self):
        """Test that prompt template includes _literature_context if present."""
        state = ThreadState(messages=[])
        # Use set_context for private fields
        state.set_context("literature_context", "<literature_context>Test literature context</literature_context>")
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Test literature context" in prompt
        assert "<literature_context>" in prompt

    def test_prompt_includes_knowledge_context(self):
        """Test that prompt template includes _knowledge_context if present."""
        state = ThreadState(messages=[])
        # Use set_context for private fields
        state.set_context("knowledge_context", "<knowledge_context>Test knowledge context</knowledge_context>")
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Test knowledge context" in prompt
        assert "<knowledge_context>" in prompt

    def test_prompt_includes_discipline_norms(self):
        """Test that prompt template includes _discipline_norms if present."""
        state = ThreadState(messages=[])
        # Use set_context for private fields
        state.set_context("discipline_norms", {
            "citation_style": "IEEE",
            "writing_style": "technical",
            "structure": ["Introduction", "Methods", "Results"],
        })
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "IEEE" in prompt
        assert "technical" in prompt
        assert "Writing Guidelines" in prompt

    def test_prompt_without_context_fields(self):
        """Test that prompt works without context fields."""
        state = ThreadState(messages=[])
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        # Should have base prompt content
        assert "AcademiaGPT" in prompt
        assert "academic research" in prompt

    def test_prompt_with_all_contexts(self):
        """Test that prompt includes all contexts when present."""
        state = ThreadState(
            messages=[],
            workspace_type="sci",
            discipline="computer_science",
        )
        # Use set_context for private fields
        state.set_context("literature_context", "<literature_context>Lit context</literature_context>")
        state.set_context("knowledge_context", "<knowledge_context>Knowledge context</knowledge_context>")
        state.set_context("discipline_norms", {
            "citation_style": "APA",
            "writing_style": "empirical",
        })
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "SCI Paper" in prompt
        assert "Computer Science" in prompt
        assert "Lit context" in prompt
        assert "Knowledge context" in prompt
        assert "APA" in prompt


class TestMakeLeadAgent:
    """Tests for make_lead_agent function."""

    def test_make_lead_agent_accepts_middlewares(self):
        """Test that make_lead_agent accepts middleware chain."""
        from unittest.mock import MagicMock, patch

        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        paper_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            paper_service=paper_service,
        )

        config = {"configurable": {"model_name": "gpt-4o"}}

        # Mock all the external dependencies
        with patch("src.models.factory.create_chat_model") as mock_model, \
             patch("src.agents.lead_agent.agent.get_available_tools") as mock_tools, \
             patch("src.agents.lead_agent.agent.create_react_agent") as mock_create_agent:

            mock_model.return_value = MagicMock()
            mock_tools.return_value = []
            mock_create_agent.return_value = MagicMock()

            agent = make_lead_agent(config, middlewares=middlewares)

            assert agent is not None
            mock_create_agent.assert_called_once()

    def test_make_lead_agent_without_middlewares(self):
        """Test that make_lead_agent works without middlewares."""
        from unittest.mock import MagicMock, patch

        config = {"configurable": {"model_name": "gpt-4o"}}

        with patch("src.models.factory.create_chat_model") as mock_model, \
             patch("src.agents.lead_agent.agent.get_available_tools") as mock_tools, \
             patch("src.agents.lead_agent.agent.create_react_agent") as mock_create_agent:

            mock_model.return_value = MagicMock()
            mock_tools.return_value = []
            mock_create_agent.return_value = MagicMock()

            agent = make_lead_agent(config)

            assert agent is not None
            mock_create_agent.assert_called_once()
