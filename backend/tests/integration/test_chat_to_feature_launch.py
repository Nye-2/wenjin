"""End-to-end: chat turn → preload middleware → prompt render → launch_feature.

These tests exist to catch the bug class that triggered the chat/lead refactor:
the chat prompt must surface DB-backed capabilities so the model picks an id
that ``launch_feature`` can actually resolve, and ``launch_feature`` must
dispatch to the v2 lead-agent execution path.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeLaunchDataServiceClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_catalog_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = True,
    ):
        capabilities = {
            "framework_outline": SimpleNamespace(
                id="framework_outline",
                workspace_type=workspace_type,
                display_name="框架大纲",
            ),
            "literature_search": SimpleNamespace(
                id="literature_search",
                workspace_type=workspace_type,
                display_name="文献检索",
            ),
        }
        return capabilities.get(capability_id)

    async def list_catalog_capabilities(self, *, workspace_type: str, enabled_only: bool = True):
        return [
            SimpleNamespace(id="framework_outline", workspace_type=workspace_type, display_name="框架大纲"),
            SimpleNamespace(id="literature_search", workspace_type=workspace_type, display_name="文献检索"),
        ]


@pytest.fixture(autouse=True)
def _patch_dataservice_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "src.dataservice_client.provider.dataservice_client",
        lambda: _FakeLaunchDataServiceClient(),
    )

# ---------------------------------------------------------------------------
# Static contract (existence) checks — fast smoke
# ---------------------------------------------------------------------------


def test_chat_turn_routes_to_lead_agent_only():
    """Sending a 'launch this feature' chat turn must reach lead_agent (no bypass)."""
    from src.application.handlers.thread_turn_handler import ThreadTurnHandler

    assert not hasattr(ThreadTurnHandler, "_try_feature_command_reply")


def test_lead_agent_can_call_launch_feature_tool():
    """Tool registry exposes launch_feature; agent can resolve it."""
    from src.agents.chat_agent.agent import get_available_tools

    tools = get_available_tools()
    by_name = {getattr(t, "name", ""): t for t in tools}
    assert "launch_feature" in by_name
    tool = by_name["launch_feature"]
    schema = getattr(tool, "args_schema", None)
    assert schema is not None
    field_names = set(schema.model_fields.keys()) if hasattr(schema, "model_fields") else set()
    assert "feature_id" in field_names
    assert "params" in field_names


# ---------------------------------------------------------------------------
# Closed-loop chain: preload middleware → prompt render → launch_feature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preload_middleware_feeds_prompt_with_capability_ids():
    """The preload middleware writes caps/skills into state, and
    apply_prompt_template reads them out into ``<available_capabilities>``.

    This is the regression that originally surfaced as "framework_outline
    暂时不可用": before the fix, only ``ainvoke`` preloaded, so the streaming
    path saw an empty catalog and the model invented invalid feature ids.
    """
    from src.agents.chat_agent.agent import apply_prompt_template
    from src.agents.middlewares.capability_skill_preload import (
        CapabilitySkillPreloadMiddleware,
    )
    from src.agents.thread_state import create_thread_state

    preloaded = (
        [
            {
                "id": "framework_outline",
                "display_name": "框架大纲",
                "description": "scientific paper framework",
                "intent_description": "",
                "trigger_phrases": ["设计框架", "写大纲"],
            },
            {
                "id": "literature_search",
                "display_name": "文献检索",
                "description": "search relevant papers",
                "intent_description": "",
                "trigger_phrases": ["检索文献", "找文献"],
            },
        ],
        [
            {
                "id": "scholar-searcher",
                "display_name": "Scholar Searcher",
                "description": "external search adapter",
                "subagent_type": "searcher",
            }
        ],
    )

    with patch.object(
        CapabilitySkillPreloadMiddleware,
        "_fetch",
        new=AsyncMock(return_value=preloaded),
    ):
        mw = CapabilitySkillPreloadMiddleware()
        state = create_thread_state({"messages": [], "workspace_type": "sci"})
        update = await mw.before_model(state, {"configurable": {}})

    assert update["available_capabilities"][0]["id"] == "framework_outline"

    state["available_capabilities"] = update["available_capabilities"]
    state["available_skills"] = update["available_skills"]
    prompt = apply_prompt_template(state, {"configurable": {}})

    # The model MUST see DB-backed ids — not the deleted legacy fallback ids.
    assert "<available_capabilities>" in prompt
    assert 'id="framework_outline"' in prompt
    assert 'id="literature_search"' in prompt
    assert "<available_features>" not in prompt  # legacy block must be gone


@pytest.mark.asyncio
async def test_launch_feature_dispatches_execution_for_known_capability():
    """The ``launch_feature`` tool must:
    - resolve workspace_type
    - look the capability up in the new DB table
    - create an ExecutionRecord and dispatch the v2 Celery task
    """
    from src.tools.builtins.launch_feature import launch_feature_tool

    fake_capability = SimpleNamespace(
        id="framework_outline",
        workspace_type="sci",
        display_name="框架大纲",
    )

    @dataclass
    class _StubExecution:
        id: str

    fake_execution = _StubExecution(id="exec-42")

    fake_execution_service = MagicMock()
    fake_execution_service.list_executions = AsyncMock(return_value=[])
    fake_execution_service.create_execution = AsyncMock(return_value=fake_execution)

    # Build an awaitable-compatible db.execute that returns the capability row
    # the first time and the available-id list shape the second.
    cap_result = MagicMock()
    cap_result.scalar_one_or_none = MagicMock(return_value=fake_capability)
    avail_result = MagicMock()
    avail_result.all = MagicMock(return_value=[])

    fake_db = MagicMock()
    fake_db.execute = AsyncMock(side_effect=[cap_result, avail_result])

    @asynccontextmanager
    async def _fake_db_session():
        yield fake_db

    fake_publish = AsyncMock()
    fake_celery = MagicMock(enabled=True)
    fake_task = MagicMock()

    with (
        patch("src.database.get_db_session", _fake_db_session),
        patch("src.services.workspace_skill_labels.list_workspace_types",
              AsyncMock(return_value={"ws-1": "sci"})),
        patch("src.services.execution_service.ExecutionService",
              return_value=fake_execution_service),
        patch("src.workspace_events.publish_workspace_event", fake_publish),
        patch("src.config.app_config.celery_settings", fake_celery),
        patch("src.task.tasks.execution.execute_execution", fake_task),
    ):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "framework_outline",
                "params": {"topic": "联邦学习+大模型"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "t-1",
                    "user_id": "u-1",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["execution_id"] == "exec-42"
    assert result["feature_id"] == "framework_outline"
    fake_execution_service.create_execution.assert_awaited_once()
    create_kwargs = fake_execution_service.create_execution.await_args.kwargs
    assert create_kwargs["thread_id"] == "t-1"
    assert create_kwargs["display_name"] == "框架大纲"
    assert create_kwargs["commit"] is False
    fake_task.apply_async.assert_called_once_with(
        args=["exec-42"], queue="long_running"
    )


@pytest.mark.asyncio
async def test_launch_feature_returns_unknown_for_invalid_capability_id():
    """A model that hallucinates a legacy feature id must receive an advisory
    listing valid alternatives — not silently succeed."""
    from src.tools.builtins.launch_feature import launch_feature_tool

    cap_result = MagicMock()
    cap_result.scalar_one_or_none = MagicMock(return_value=None)
    avail_result = MagicMock()
    avail_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            id="framework_outline",
            workspace_type="sci",
            display_name="框架大纲",
        ),
        SimpleNamespace(
            id="literature_search",
            workspace_type="sci",
            display_name="文献检索",
        ),
    ]

    fake_db = MagicMock()
    fake_db.execute = AsyncMock(side_effect=[cap_result, avail_result])

    @asynccontextmanager
    async def _fake_db_session():
        yield fake_db

    with (
        patch("src.database.get_db_session", _fake_db_session),
        patch("src.services.workspace_skill_labels.list_workspace_types",
              AsyncMock(return_value={"ws-1": "sci"})),
    ):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "thesis_writing",  # legacy id, no longer exists
                "params": {},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "t-1",
                    "user_id": "u-1",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "unknown_feature"
    assert "framework_outline" in result["detail"]
    assert "literature_search" in result["detail"]
