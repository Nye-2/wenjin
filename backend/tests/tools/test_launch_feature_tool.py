"""Tests for the `launch_feature` builtin tool — v2 execution pipeline."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtins import launch_feature_tool


@dataclass
class _StubExecution:
    id: str


@asynccontextmanager
async def _fake_db_session():
    yield MagicMock()


@pytest.mark.asyncio
async def test_launch_feature_creates_execution_and_dispatches():
    """Tool must create an ExecutionRecord and dispatch the v2 Celery task."""
    fake_execution = _StubExecution(id="exec-1")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)

    fake_publish = AsyncMock()
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_task = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.workspace_events.publish_workspace_event", fake_publish), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.tasks.execution.execute_execution", fake_task):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "paper_analysis",
                "params": {"paper_title": "联邦学习结合大模型微调"},
                "skill_id": "paper-analyst",
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["execution_id"] == "exec-1"
    assert result["feature_id"] == "paper_analysis"
    fake_service.create_execution.assert_awaited_once()
    fake_task.apply_async.assert_called_once_with(
        args=["exec-1"],
        queue="long_running",
    )


@pytest.mark.asyncio
async def test_launch_feature_returns_lead_busy_when_active():
    """If there's an active execution, return advisory lead_busy."""
    @dataclass
    class _ActiveExecution:
        id: str
        feature_id: str
        progress: int

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(
        return_value=[_ActiveExecution(id="exec-0", feature_id="writing", progress=50)]
    )

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "deep_research", "params": {}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "advisory"
    assert result["code"] == "lead_busy"


@pytest.mark.asyncio
async def test_launch_feature_requires_workspace_in_config():
    """Tool fails fast if config lacks workspace_id (caller bug)."""
    with pytest.raises(ValueError, match="workspace_id"):
        await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={"configurable": {"thread_id": "th-1", "user_id": "u-1"}},
        )
