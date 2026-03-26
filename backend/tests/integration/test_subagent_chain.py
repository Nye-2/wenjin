"""Integration tests for subagent chain execution.

Note: Full chain execution tests (testing multiple subagents working together
in sequence) will be added in Phase 3 as part of the Deep Research Skill rewrite.
The current tests validate individual subagent components that will form chains.
"""

import pytest

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.academic.registry import SubagentConfig, registry


class TestSubagentChainIntegration:
    def test_registry_has_academic_subagents(self):
        """Academic subagent types should be registered."""
        assert registry.get("scout") is not None
        assert registry.get("writer") is not None
        assert registry.get("synthesizer") is not None

    @pytest.mark.asyncio
    async def test_executor_completes_without_legacy_event_stream(self):
        """Executor should focus on execution while manager owns event publication."""
        from unittest.mock import MagicMock, patch

        config = SubagentConfig(
            name="Test",
            description="Test",
            system_prompt="Reply with OK",
        )
        executor = SubagentExecutor(config=config, tools=[])

        with patch.object(executor, "_create_agent") as mock_create:
            mock_agent = MagicMock()
            async def _astream(*args, **kwargs):
                yield {"messages": [MagicMock(content="OK")]}

            mock_agent.astream = _astream
            mock_create.return_value = mock_agent

            result = await executor.aexecute("test task")

            assert result.status == SubagentStatus.COMPLETED
            assert result.result == "OK"

    def test_subagent_config_model_instantiation(self):
        """Subagent config models should instantiate with expected values."""
        from src.config.config_loader import SubagentsConfig, SubagentTypeConfig

        # Test the config models directly (avoids full config loading issues)
        subagent_config = SubagentsConfig(
            enabled=True,
            max_concurrent=4,
            types={
                "scout": SubagentTypeConfig(
                    description="Literature search and evidence collection",
                    allowed_tools=["semantic_scholar_search", "web_search", "read_file"],
                    max_turns=10,
                    timeout=300,
                ),
            },
        )
        assert subagent_config.enabled is True
        assert "scout" in subagent_config.types
        assert subagent_config.types["scout"].max_turns > 0


class TestMemoryIntegration:
    @pytest.mark.asyncio
    async def test_memory_capture_callback_uses_canonical_persistence(self):
        """Memory capture should hand off cleaned transcript to canonical persistence."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from langchain_core.messages import AIMessage, HumanMessage

        from src.agents.memory.capture import enqueue_memory_capture

        queue = MagicMock()
        messages = [
            HumanMessage(content="I study NLP"),
            AIMessage(content="I'll help with NLP research"),
        ]

        with patch(
            "src.agents.memory.capture.extract_and_persist_knowledge",
            AsyncMock(),
        ) as mock_persist:
            enqueue_memory_capture(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                messages=messages,
                source="test",
                queue=queue,
            )

            callback = queue.enqueue.call_args.kwargs["callback"]
            await callback("thread-1", messages)

        mock_persist.assert_awaited_once_with(
            "user-1",
            "user: I study NLP\nassistant: I'll help with NLP research",
            workspace_context="ws-1",
            source="test",
        )
