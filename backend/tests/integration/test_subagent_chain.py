"""Integration tests for subagent chain execution.

Note: Full chain execution tests (testing multiple subagents working together
in sequence) will be added in Phase 3 as part of the Deep Research Skill rewrite.
The current tests validate individual subagent components that will form chains.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.academic.registry import registry
from src.subagents.config import SubagentConfig
from src.subagents.manager import GlobalSubagentManager
from src.subagents.models import SubagentStatus, SubagentTask


class TestSubagentChainIntegration:
    def test_registry_has_academic_subagents(self):
        """Academic subagent types should be registered."""
        assert registry.get("scout") is not None
        assert registry.get("writer") is not None
        assert registry.get("synthesizer") is not None

    @pytest.mark.asyncio
    async def test_manager_completes_subagent_with_canonical_runtime(self):
        """Manager-backed execution should replace the retired executor path."""
        manager = GlobalSubagentManager(
            SubagentConfig(llm=MagicMock(), default_tools=[])
        )
        task = SubagentTask(
            task_id="task-1",
            thread_id="thread-1",
            prompt="test task",
            created_at=datetime.now(),
            timeout=60,
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="OK")]}
        )

        with patch.object(manager._graph_registry, "get", return_value=mock_graph):
            await manager.spawn(task)
            result = await manager.wait_for_completion("thread-1", "task-1")

        assert result is not None
        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "OK"

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
                    allowed_tools=["search_workspace_references", "web_search", "read_file"],
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
            "src.services.memory_capture_service.extract_and_persist_knowledge",
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

        mock_persist.assert_awaited_once()
        assert mock_persist.await_args.args == (
            "user-1",
            "user: I study NLP\nassistant: I'll help with NLP research",
        )
        assert mock_persist.await_args.kwargs["workspace_context"] == "ws-1"
        assert mock_persist.await_args.kwargs["source"].startswith("test#")
