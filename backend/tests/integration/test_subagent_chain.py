"""Integration tests for subagent chain execution.

Note: Full chain execution tests (testing multiple subagents working together
in sequence) will be added in Phase 3 as part of the Deep Research Skill rewrite.
The current tests validate individual subagent components that will form chains.
"""

import pytest

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.registry import SubagentConfig, registry
from src.subagents.events import EventStream, SubagentEvent, SubagentEventType


class TestSubagentChainIntegration:
    def test_registry_has_academic_subagents(self):
        """Academic subagent types should be registered."""
        assert registry.get("scout") is not None
        assert registry.get("writer") is not None
        assert registry.get("synthesizer") is not None

    @pytest.mark.asyncio
    async def test_executor_with_event_stream(self):
        """Executor should emit events to stream."""
        from unittest.mock import patch, MagicMock

        config = SubagentConfig(
            name="Test",
            description="Test",
            system_prompt="Reply with OK",
        )
        executor = SubagentExecutor(config=config, tools=[])

        stream = EventStream()

        with patch.object(executor, "_create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {"messages": [MagicMock(content="OK")]}
            mock_create.return_value = mock_agent

            result = executor.execute("test task", stream=stream)

            # Close stream to signal end of events
            stream.close()

            # Collect events
            events = []
            for event in stream.iterate(timeout=1.0):
                events.append(event)

            assert result.status == SubagentStatus.COMPLETED
            # Events should include STARTED, RUNNING, COMPLETED
            assert len(events) >= 1
            # Verify all expected event types are present
            event_types = [e.type for e in events]
            assert SubagentEventType.STARTED in event_types
            assert SubagentEventType.RUNNING in event_types
            assert SubagentEventType.COMPLETED in event_types

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
    async def test_memory_update_integration(self, tmp_path):
        """Memory system should integrate with pipeline."""
        from src.agents.memory.updater import MemoryUpdater
        from langchain_core.messages import HumanMessage, AIMessage

        storage = str(tmp_path / "memory.json")
        updater = MemoryUpdater(storage_path=storage)

        messages = [
            HumanMessage(content="I study NLP"),
            AIMessage(content="I'll help with NLP research"),
        ]

        # Update should not raise
        result = await updater.update_from_messages(messages)
        assert isinstance(result, bool)
