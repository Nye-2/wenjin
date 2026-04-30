"""Tests for chat runtime index-service wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.application.handlers.thread_turn_handler import _build_thread_agent_runtime


def test_build_thread_agent_runtime_passes_index_service_to_pipeline() -> None:
    request = SimpleNamespace(
        workspace_id="ws-1",
        model="test-model",
        attachments=(),
        thinking_enabled=False,
        reasoning_effort=None,
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        skill=None,
        model="test-model",
        messages=[],
    )
    index_service = MagicMock()

    with (
        patch(
            "src.application.handlers.thread_turn_handler.route_chat_model",
            return_value="test-model",
        ),
        patch(
            "src.application.handlers.thread_turn_handler.build_thread_runtime_config",
            return_value={"configurable": {}},
        ),
        patch(
            "src.application.handlers.thread_turn_handler.build_thread_initial_state",
            return_value={},
        ),
        patch(
            "src.agents.lead_agent.agent.build_pipeline",
            return_value=[],
        ) as build_pipeline,
    ):
        _build_thread_agent_runtime(
            request,
            thread,
            actor_id="user-1",
            workspace_service=None,
            index_service=index_service,
            artifact_service=None,
            reference_service=None,
        )

    assert build_pipeline.call_args.kwargs["index_service"] is index_service
