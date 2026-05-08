"""Tests for the `launch_feature` builtin tool."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtins import launch_feature_tool


@dataclass
class _StubFeatureLaunchResult:
    execution_session_id: str
    outcome: Any


@dataclass
class _StubFeatureTaskSubmission:
    task_id: str
    feature_id: str
    message: str


@asynccontextmanager
async def _fake_db_session():
    yield MagicMock()


@pytest.mark.asyncio
async def test_launch_feature_invokes_feature_launch_service():
    """Tool must build a FeatureLaunchCommand and call FeatureLaunchService.launch()."""
    submission = _StubFeatureTaskSubmission(
        task_id="task-abc",
        feature_id="paper_analysis",
        message="started",
    )
    fake_result = _StubFeatureLaunchResult(
        execution_session_id="es-xyz",
        outcome=submission,
    )
    fake_service = AsyncMock()
    fake_service.launch = AsyncMock(return_value=fake_result)

    with patch(
        "src.tools.builtins.launch_feature.build_feature_ingress_service",
        return_value=fake_service,
    ), patch(
        "src.tools.builtins.launch_feature.get_db_session",
        _fake_db_session,
    ):
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
    assert result["task_id"] == "task-abc"
    assert result["feature_id"] == "paper_analysis"
    assert result["execution_session_id"] == "es-xyz"
    fake_service.launch.assert_awaited_once()
    cmd = fake_service.launch.await_args.args[0]
    assert cmd.workspace_id == "ws-1"
    assert cmd.feature_id == "paper_analysis"
    assert cmd.thread_id == "th-1"
    assert cmd.skill_id == "paper-analyst"
    assert cmd.params == {"paper_title": "联邦学习结合大模型微调"}
    assert cmd.launch_source == "thread"


@pytest.mark.asyncio
async def test_launch_feature_returns_warning_when_advisory():
    """If FeatureLaunchService returns an advisory outcome, surface its code."""

    @dataclass
    class _Advisory:
        code: str
        message: str

    fake_result = _StubFeatureLaunchResult(
        execution_session_id="es-1",
        outcome=_Advisory(code="literature_insufficient", message="文献不足"),
    )
    fake_service = AsyncMock()
    fake_service.launch = AsyncMock(return_value=fake_result)

    with patch(
        "src.tools.builtins.launch_feature.build_feature_ingress_service",
        return_value=fake_service,
    ), patch(
        "src.tools.builtins.launch_feature.get_db_session",
        _fake_db_session,
    ):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "writing", "params": {"topic": "x"}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "advisory"
    assert result["code"] == "literature_insufficient"
    assert result["execution_session_id"] == "es-1"


@pytest.mark.asyncio
async def test_launch_feature_requires_workspace_in_config():
    """Tool fails fast if config lacks workspace_id (caller bug)."""
    with pytest.raises(ValueError, match="workspace_id"):
        await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={"configurable": {"thread_id": "th-1", "user_id": "u-1"}},
        )
