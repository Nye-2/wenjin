"""Tests for shared subagent task-building helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from src.subagents.config import SubagentConfig
from src.subagents.context_snapshot import build_subagent_context_snapshot
from src.subagents.task_builder import (
    SubagentRuntimeContext,
    build_subagent_metadata,
    build_subagent_task,
)


def _manager_config() -> SubagentConfig:
    return SubagentConfig(
        default_timeout=900,
        max_timeout=3600,
        default_max_turns=10,
        max_turns_limit=50,
    )


class TestSubagentRuntimeContext:
    def test_from_mapping_normalizes_optional_values(self):
        context = SubagentRuntimeContext.from_mapping(
            {
                "thread_id": " thread-1 ",
                "workspace_id": " ",
                "user_id": "user-1",
                "model_name": "gpt-4o",
                "trace_id": None,
            }
        )

        assert context.thread_id == "thread-1"
        assert context.workspace_id is None
        assert context.user_id == "user-1"
        assert context.model_name == "gpt-4o"

    def test_resolve_thread_id_uses_trace_suffix_when_detached(self):
        context = SubagentRuntimeContext.from_mapping({"trace_id": "trace-1"})

        assert context.resolve_thread_id(fallback_prefix="parallel-plan") == "parallel-plan-trace-1"


class TestSubagentMetadata:
    def test_build_subagent_metadata_respects_inclusion_flags(self):
        context = SubagentRuntimeContext.from_mapping(
            {
                "thread_id": "thread-1",
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "model_name": "gpt-4o",
            }
        )

        metadata = build_subagent_metadata(
            description="Search papers",
            subagent_type="scout",
            system_prompt="You are Scout.",
            runtime_context=context,
            include_workspace=True,
            include_user=False,
        )

        assert metadata == {
            "description": "Search papers",
            "subagent_type": "scout",
            "system_prompt": "You are Scout.",
            "workspace_id": "ws-1",
            "model_name": "gpt-4o",
        }

    def test_build_subagent_metadata_appends_context_snapshot_to_system_prompt(self):
        context = SubagentRuntimeContext.from_mapping({"workspace_id": "ws-1"})

        metadata = build_subagent_metadata(
            subagent_type="scout",
            system_prompt="You are Scout.",
            context_snapshot="## Inherited Workspace Context\n- workspace_type: sci",
            runtime_context=context,
            include_workspace=True,
        )

        assert "You are Scout." in metadata["system_prompt"]
        assert "## Inherited Workspace Context" in metadata["system_prompt"]


class TestSubagentTaskBuilder:
    def test_build_subagent_task_clamps_runtime_limits(self):
        task = build_subagent_task(
            _manager_config(),
            prompt="Find papers",
            thread_id="thread-1",
            fallback_max_turns=10,
            requested_max_turns=99,
            requested_timeout=9999,
            tools=["semantic_scholar_search"],
            metadata={"subagent_type": "scout", "workspace_id": "ws-1"},
        )

        assert task.thread_id == "thread-1"
        assert task.max_turns == 50
        assert task.timeout == 3600
        assert task.tools == ["semantic_scholar_search"]
        assert task.metadata["workspace_id"] == "ws-1"


class TestContextSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_skips_db_fallback_when_state_is_already_populated(self):
        runtime_context = SubagentRuntimeContext.from_mapping(
            {
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "thread_id": "thread-1",
            }
        )
        state = {
            "workspace_type": "sci",
            "discipline": "computer_science",
            "literature_context": "## 文献库概览\nPaper A",
            "current_skill": "framework-designer",
        }

        with patch(
            "src.subagents.context_snapshot._load_db_snapshot",
            AsyncMock(return_value={"workspace_type": "should-not-be-used"}),
        ) as load_db_snapshot:
            snapshot = await build_subagent_context_snapshot(
                runtime_context=runtime_context,
                state=state,
            )

        load_db_snapshot.assert_not_awaited()
        assert snapshot is not None
        assert "workspace_type: sci" in snapshot
