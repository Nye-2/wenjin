"""Tests for Lead Agent middleware chain integration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

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
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class TestBuildMiddlewares:
    """Tests for build_middlewares function."""

    def test_build_middlewares_creates_all_five(self):
        """Test that build_middlewares creates all 5 middlewares when services provided."""
        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        reference_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            reference_service=reference_service,
        )

        assert len(middlewares) == 5

    def test_build_middlewares_order_is_correct(self):
        """Test that middleware order is correct."""
        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        reference_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            reference_service=reference_service,
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
        """Test that prompt template includes literature_context if present."""
        state = ThreadState(
            messages=[],
            literature_context="<literature_context>Test literature context</literature_context>",
        )
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Test literature context" in prompt
        assert "<literature_context>" in prompt

    def test_prompt_includes_knowledge_context(self):
        """Test that prompt template includes knowledge_context if present."""
        state = ThreadState(
            messages=[],
            knowledge_context="<knowledge_context>Test knowledge context</knowledge_context>",
        )
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Test knowledge context" in prompt
        assert "<knowledge_context>" in prompt

    def test_prompt_includes_memory_context(self):
        """Test that prompt template includes long-term memory context if present."""
        state = ThreadState(
            messages=[],
            memory_context="<academic_memory>偏好 IEEE</academic_memory>",
        )
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "偏好 IEEE" in prompt
        assert "<academic_memory>" in prompt

    def test_prompt_includes_discipline_norms(self):
        """Test that prompt template includes discipline_norms if present."""
        state = ThreadState(
            messages=[],
            discipline_norms={
                "citation_style": "IEEE",
                "writing_style": "technical",
                "structure": ["Introduction", "Methods", "Results"],
            },
        )
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
        assert "Wenjin" in prompt
        assert "chat-side academic workspace assistant" in prompt
        assert "Chat Panel Contract" in prompt
        assert "not the long-running Compute executor" in prompt
        assert "produce a concise Compute feature proposal" in prompt
        assert "answer it directly first" in prompt
        assert "Do not give generic self-introductions" in prompt
        assert "do not ask the user to repeat information" in prompt
        assert "Avoid generic prompts like" in prompt
        assert "Subagent delegation for complex multi-step tasks" not in prompt

    def test_prompt_with_all_contexts(self):
        """Test that prompt includes all contexts when present."""
        state = ThreadState(
            messages=[],
            workspace_type="sci",
            discipline="computer_science",
            literature_context="<literature_context>Lit context</literature_context>",
            memory_context="<academic_memory>Memory context</academic_memory>",
            knowledge_context="<knowledge_context>Knowledge context</knowledge_context>",
            discipline_norms={
                "citation_style": "APA",
                "writing_style": "empirical",
            },
        )
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "学术论文（SCI/EI）" in prompt
        assert "Computer Science" in prompt
        assert "Lit context" in prompt
        assert "Memory context" in prompt
        assert "Knowledge context" in prompt
        assert "APA" in prompt

    def test_prompt_truncates_large_context_blocks(self):
        """Large prompt-side context blocks should be bounded to protect token budget."""
        long_lit = "<literature_context>" + ("A" * 5000) + "</literature_context>"
        long_knowledge = "<knowledge_context>" + ("B" * 5000) + "</knowledge_context>"
        long_memory = "<academic_memory>" + ("C" * 4000) + "</academic_memory>"
        state = ThreadState(
            messages=[],
            literature_context=long_lit,
            knowledge_context=long_knowledge,
            memory_context=long_memory,
        )
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "...[truncated]" in prompt
        assert len(prompt) < 12000

    def test_prompt_scopes_available_skills_to_workspace(self):
        """Test that available skills are rendered from the workspace chat catalog."""
        state = ThreadState(messages=[], workspace_type="sci")
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Available Skills" in prompt
        assert "deep-research -> literature_search" in prompt
        assert "peer-reviewer -> peer_review" in prompt
        assert "journal-recommender -> journal_recommend" in prompt
        assert "fullpaper-writer" not in prompt
        assert "proposal-writer" not in prompt

    def test_prompt_omits_available_skills_when_workspace_has_no_thread_skill_catalog(self):
        """Test that prompt renders the current workspace chat skill catalog."""
        state = ThreadState(messages=[], workspace_type="patent")
        config = {"configurable": {}}

        prompt = apply_prompt_template(state, config)

        assert "Available Skills" in prompt
        assert "patent-drafter -> patent_outline" in prompt

    def test_prompt_includes_selected_skill_bound_feature(self):
        """Selected skill guidance should explicitly state the bound feature."""
        state = ThreadState(messages=[], workspace_type="sci")
        config = {"configurable": {"selected_skill": "framework-designer"}}

        prompt = apply_prompt_template(state, config)

        assert "The user selected `framework-designer`" in prompt
        assert "Bound feature: `framework_outline`." in prompt
        assert "run_workspace_feature" not in prompt
        assert "feature proposal" in prompt


class TestMakeLeadAgent:
    """Tests for make_lead_agent function."""

    class _InjectMemoryMiddleware(Middleware):
        async def before_model(self, state, config):
            return {"memory_context": "<academic_memory>偏好 IEEE</academic_memory>"}

    class _InjectAcademicContextMiddleware(Middleware):
        async def before_model(self, state, config):
            return {
                "workspace_type": "sci",
                "discipline": "computer_science",
                "literature_context": "<literature_context>TOC summary</literature_context>",
                "knowledge_context": "<knowledge_context>Framework A</knowledge_context>",
                "current_skill": "framework-designer",
                "discipline_norms": {
                    "citation_style": "IEEE",
                    "writing_style": "technical and precise",
                },
            }

    class _CaptureChatModel(BaseChatModel):
        _captured_messages: object | None = PrivateAttr(default=None)

        @property
        def _llm_type(self) -> str:
            return "capture-chat-model"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self._captured_messages = messages
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            self._captured_messages = messages
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )

    def test_make_lead_agent_accepts_middlewares(self):
        """Test that make_lead_agent accepts middleware chain."""
        from unittest.mock import MagicMock, patch

        from src.agents.lead_agent.dynamic_tools import DynamicToolNode

        workspace_service = MagicMock()
        index_service = MagicMock()
        artifact_service = MagicMock()
        reference_service = MagicMock()

        middlewares = build_middlewares(
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            reference_service=reference_service,
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
            args, kwargs = mock_create_agent.call_args
            assert callable(args[0])
            assert isinstance(args[1], DynamicToolNode)
            assert kwargs["state_schema"] is ThreadState
            assert "checkpointer" in kwargs

    def test_make_lead_agent_without_middlewares(self):
        """Test that make_lead_agent works without middlewares."""
        from src.config.config_loader import MiddlewaresConfig, SummarizationConfig

        config = {"configurable": {"model_name": "gpt-4o"}}

        # Create mock app config with summarization disabled
        mock_app_config = MagicMock()
        mock_app_config.middlewares = MiddlewaresConfig(
            summarization=SummarizationConfig(enabled=False)
        )

        with patch("src.models.factory.create_chat_model") as mock_model, \
             patch("src.agents.lead_agent.agent.get_available_tools") as mock_tools, \
             patch("src.agents.lead_agent.agent.create_react_agent") as mock_create_agent, \
             patch("src.config.config_loader.get_app_config", return_value=mock_app_config):

            mock_model.return_value = MagicMock()
            mock_tools.return_value = []
            mock_create_agent.return_value = MagicMock()

            agent = make_lead_agent(config)

            assert agent is not None
            mock_create_agent.assert_called_once()

    def test_make_lead_agent_prompt_callable_preserves_thread_messages(self):
        """Prompt callable must prepend a system message instead of replacing history."""
        fake_agent = MagicMock()

        with patch(
            "src.models.factory.create_chat_model",
            return_value=MagicMock(),
        ), patch(
            "src.agents.lead_agent.agent.get_available_tools",
            return_value=[],
        ), patch(
            "src.agents.lead_agent.agent.create_react_agent",
            return_value=fake_agent,
        ) as mock_create_agent:
            make_lead_agent({"configurable": {"model_name": "gpt-4o"}}, middlewares=[])

        prompt_fn = mock_create_agent.call_args.kwargs["prompt"]
        rendered = prompt_fn({"messages": [HumanMessage(content="如何做实验设计？")]})

        assert isinstance(rendered[0], SystemMessage)
        assert "Wenjin" in rendered[0].content
        assert isinstance(rendered[1], HumanMessage)
        assert rendered[1].content == "如何做实验设计？"

    @pytest.mark.asyncio
    async def test_make_lead_agent_runtime_prompt_includes_thread_state_context(self):
        """Runtime-injected ThreadState context should survive into the final model prompt."""
        capture_model = self._CaptureChatModel()

        with patch(
            "src.models.factory.create_chat_model",
            return_value=capture_model,
        ), patch(
            "src.agents.lead_agent.agent.get_available_tools",
            return_value=[],
        ):
            agent = make_lead_agent(
                {"configurable": {"model_name": "gpt-4o"}},
                middlewares=[
                    self._InjectMemoryMiddleware(),
                    self._InjectAcademicContextMiddleware(),
                ],
            )
            await agent.ainvoke(
                {"messages": [HumanMessage(content="如何做实验设计？")]},
                config={"configurable": {"model_name": "gpt-4o", "thread_id": "thread-1"}},
            )

        system_prompt = capture_model._captured_messages[0].content
        assert "学术论文（SCI/EI）" in system_prompt
        assert "Computer Science" in system_prompt
        assert "TOC summary" in system_prompt
        assert "Framework A" in system_prompt
        assert "偏好 IEEE" in system_prompt
        assert "framework-designer" in system_prompt
        assert "Citation Style: IEEE" in system_prompt
        assert capture_model._captured_messages[1].content == "如何做实验设计？"

    def test_make_lead_agent_defaults_vision_from_default_model(self):
        """Default model resolution should happen before inferring vision support."""
        fake_agent = MagicMock()

        with patch(
            "src.agents.lead_agent.agent.get_default_model_id",
            return_value="gpt-4o",
        ), patch(
            "src.agents.lead_agent.agent.model_supports_vision",
            side_effect=lambda model_name: str(model_name).startswith("gpt-4o"),
        ), patch(
            "src.models.factory.create_chat_model"
        ) as mock_model, patch(
            "src.agents.lead_agent.agent.get_available_tools",
            return_value=[],
        ), patch(
            "src.agents.lead_agent.agent.create_react_agent",
            return_value=fake_agent,
        ):
            mock_model.return_value = MagicMock()

            agent = make_lead_agent({"configurable": {}}, middlewares=[])

        configurable = agent._default_config["configurable"]
        assert configurable["model_name"] == "gpt-4o"
        assert configurable["supports_vision"] is True

    @pytest.mark.asyncio
    async def test_make_lead_agent_recomputes_vision_for_runtime_model_override(self):
        """Runtime model overrides should not inherit stale vision flags."""
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(return_value={"messages": []})

        with patch(
            "src.agents.lead_agent.agent.model_supports_vision",
            side_effect=lambda model_name: str(model_name).startswith("gpt-4o"),
        ), patch(
            "src.models.factory.create_chat_model"
        ) as mock_model, patch(
            "src.agents.lead_agent.agent.get_available_tools",
            return_value=[],
        ), patch(
            "src.agents.lead_agent.agent.create_react_agent",
            return_value=fake_agent,
        ):
            mock_model.return_value = MagicMock()

            agent = make_lead_agent(
                {"configurable": {"model_name": "gpt-4o"}},
                middlewares=[],
            )
            await agent.ainvoke(
                {"messages": []},
                config={"configurable": {"model_name": "qwen3.5-plus"}},
            )

        runtime_config = fake_agent.ainvoke.await_args.kwargs["config"]
        assert runtime_config["configurable"]["model_name"] == "qwen3.5-plus"
        assert runtime_config["configurable"]["supports_vision"] is False

    @pytest.mark.asyncio
    async def test_make_lead_agent_applies_before_model_middlewares_on_invoke(self):
        """Runtime middleware chain should modify the state before agent execution."""
        config = {"configurable": {"model_name": "gpt-4o"}}
        fake_agent = MagicMock()
        fake_agent.ainvoke = AsyncMock(return_value={"messages": []})

        with patch("src.models.factory.create_chat_model") as mock_model, \
             patch("src.agents.lead_agent.agent.get_available_tools", return_value=[]), \
             patch("src.agents.lead_agent.agent.create_react_agent", return_value=fake_agent):
            mock_model.return_value = MagicMock()

            agent = make_lead_agent(
                config,
                middlewares=[self._InjectMemoryMiddleware()],
            )
            await agent.ainvoke({"messages": []}, config=config)

        invoked_state = fake_agent.ainvoke.await_args.args[0]
        assert invoked_state["memory_context"] == "<academic_memory>偏好 IEEE</academic_memory>"

    @pytest.mark.asyncio
    async def test_make_lead_agent_astream_with_result_yields_tokens_and_final_state(self):
        """Streaming wrapper should preserve middleware application and final result capture."""
        config = {"configurable": {"model_name": "gpt-4o"}}

        class _FakeCompiledAgent:
            async def astream(self, *args, **kwargs):
                yield (
                    "messages",
                    (
                        SimpleNamespace(content="hello "),
                        {"langgraph_node": "agent"},
                    ),
                )
                yield (
                    "messages",
                    (
                        SimpleNamespace(content="world"),
                        {"langgraph_node": "agent"},
                    ),
                )
                yield ("values", {"messages": [SimpleNamespace(content="hello world")]})

        with patch("src.models.factory.create_chat_model") as mock_model, \
             patch("src.agents.lead_agent.agent.get_available_tools", return_value=[]), \
             patch("src.agents.lead_agent.agent.create_react_agent", return_value=_FakeCompiledAgent()):
            mock_model.return_value = MagicMock()

            agent = make_lead_agent(
                config,
                middlewares=[self._InjectMemoryMiddleware()],
            )
            stream_run = agent.astream_with_result(
                {"messages": []},
                config=config,
                stream_mode=["messages", "values"],
            )
            chunks = [item async for item in stream_run]
            result = await stream_run.result()

        assert chunks[0][0] == "messages"
        assert chunks[-1][0] == "values"
        assert result["messages"][0].content == "hello world"
