"""Tests for the `launch_feature` builtin tool — v2 execution pipeline."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtins import launch_feature_tool


@dataclass
class _StubExecution:
    id: str


def _capability(capability_id: str = "paper_analysis") -> MagicMock:
    cap = MagicMock()
    cap.id = capability_id
    cap.workspace_type = "thesis"
    cap.display_name = "Paper Analysis"
    return cap


@asynccontextmanager
async def _fake_db_session():
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=_capability())
    db.execute = AsyncMock(return_value=result)
    yield db


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
    create_kwargs = fake_service.create_execution.await_args.kwargs
    assert create_kwargs["execution_type"] == "feature"
    assert create_kwargs["thread_id"] == "th-1"
    assert create_kwargs["display_name"] == "Paper Analysis"
    assert create_kwargs["commit"] is False
    fake_task.apply_async.assert_called_once_with(
        args=["exec-1"],
        queue="long_running",
    )


@pytest.mark.asyncio
async def test_launch_feature_uses_selected_skill_from_runtime_config_when_tool_args_omit_it():
    """Chat-selected skill should survive into the launched execution."""
    fake_execution = _StubExecution(id="exec-2")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_task = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.tasks.execution.execute_execution", fake_task):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "paper_analysis",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "paper-analyst",
                }
            },
        )

    assert result["status"] == "launched"
    fake_service.create_execution.assert_awaited_once()
    create_kwargs = fake_service.create_execution.await_args.kwargs
    assert create_kwargs["entry_skill_id"] == "paper-analyst"


@pytest.mark.asyncio
async def test_launch_feature_reuses_execution_id_from_runtime_config_for_resume():
    """Resume flows should dispatch the existing execution instead of creating a new one."""
    fake_execution = _StubExecution(id="exec-9")
    fake_execution.workspace_id = "ws-1"  # type: ignore[attr-defined]
    fake_execution.user_id = "user-1"  # type: ignore[attr-defined]
    fake_execution.feature_id = "paper_analysis"  # type: ignore[attr-defined]
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock(return_value=fake_execution)
    fake_service.create_execution = AsyncMock()
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_task = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.tasks.execution.execute_execution", fake_task):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "paper_analysis",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "paper-analyst",
                    "execution_id": "exec-9",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["execution_id"] == "exec-9"
    fake_service.create_execution.assert_not_called()
    fake_service.update_execution.assert_awaited_once()
    update_kwargs = fake_service.update_execution.await_args.kwargs
    assert update_kwargs["status"] == "pending"
    assert update_kwargs["thread_id"] == "th-1"
    assert update_kwargs["entry_skill_id"] == "paper-analyst"
    assert update_kwargs["params"]["brief"]["capability_id"] == "paper_analysis"


@pytest.mark.asyncio
async def test_launch_feature_rejects_resume_execution_id_from_another_workspace():
    """Resume must not mutate executions outside the current workspace/user scope."""
    foreign_execution = MagicMock()
    foreign_execution.id = "exec-foreign"
    foreign_execution.workspace_id = "ws-2"
    foreign_execution.user_id = "user-2"
    foreign_execution.feature_id = "paper_analysis"

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=foreign_execution)
    fake_service.update_execution = AsyncMock()
    fake_service.create_execution = AsyncMock()
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_task = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.tasks.execution.execute_execution", fake_task):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "paper_analysis",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "paper-analyst",
                    "execution_id": "exec-foreign",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "unknown_execution"
    assert result["execution_id"] == "exec-foreign"
    fake_service.update_execution.assert_not_called()
    fake_service.create_execution.assert_not_called()
    fake_task.apply_async.assert_not_called()


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
    assert result["execution_id"] == "exec-0"


@pytest.mark.asyncio
async def test_launch_feature_returns_error_when_celery_disabled():
    """Tool must not create a fake running execution if workers are unavailable."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_celery = MagicMock(enabled=False)

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "execution_backend_unavailable"
    fake_service.create_execution.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_returns_missing_params_advisory_before_execution_creation():
    """Shared launch context rules should prevent empty thread/tool launches."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_celery = MagicMock(enabled=True)

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.config.app_config.celery_settings", fake_celery), \
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
    assert result["code"] == "missing_params"
    fake_service.create_execution.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_returns_error_when_queue_dispatch_fails():
    """Queue submission failures should not leave a fake launched execution."""
    fake_execution = _StubExecution(id="exec-1")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_service.complete_execution = AsyncMock()
    fake_celery = MagicMock(enabled=True)
    fake_task = MagicMock()
    fake_task.apply_async.side_effect = RuntimeError("queue down")

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.tasks.execution.execute_execution", fake_task):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "execution_queue_unavailable"


@pytest.mark.asyncio
async def test_launch_feature_requires_workspace_in_config():
    """Tool fails fast if config lacks workspace_id (caller bug)."""
    with pytest.raises(ValueError, match="workspace_id"):
        await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={"configurable": {"thread_id": "th-1", "user_id": "u-1"}},
        )
