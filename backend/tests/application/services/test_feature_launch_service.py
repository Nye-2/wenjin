"""Tests for unified feature launch service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.commands import FeatureLaunchCommand
from src.application.errors import NotFoundError
from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission
from src.application.services.feature_launch_service import FeatureIngressService


def _workspace(workspace_type: str = "sci"):
    return SimpleNamespace(
        id="ws-1",
        user_id="user-1",
        type=SimpleNamespace(value=workspace_type),
    )


def _feature(feature_id: str):
    return SimpleNamespace(id=feature_id)


def _execution_record(
    execution_id: str,
    *,
    workspace_id: str = "ws-1",
    feature_id: str = "framework_outline",
    thread_id: str | None = "thread-1",
    entry_skill_id: str | None = "framework-designer",
    workspace_type: str = "sci",
    params: dict | None = None,
    user_id: str = "user-1",
):
    return SimpleNamespace(
        id=execution_id,
        user_id=user_id,
        workspace_id=workspace_id,
        feature_id=feature_id,
        thread_id=thread_id,
        entry_skill_id=entry_skill_id,
        workspace_type=workspace_type,
        params=params or {},
    )


def _compute_sessions():
    service = AsyncMock()
    service.ensure_for_execution = AsyncMock(
        return_value=SimpleNamespace(id="compute-1")
    )
    return service


@pytest.mark.asyncio
async def test_launch_creates_execution_and_passes_id_to_handler():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-1",
            feature_id="framework_outline",
            message="Queued 框架与摘要",
        )
    )
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    execution_service.create_execution = AsyncMock(
        return_value=_execution_record("execution-1")
    )
    execution_service.update_execution = AsyncMock()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("framework_outline"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                feature_id="framework_outline",
                params={"topic": "agents"},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="开始写框架",
            )
        )

    assert result.execution_id == "execution-1"
    handler.execute.assert_awaited_once()
    assert handler.execute.await_args.kwargs["execution_id"] == "execution-1"
    compute_sessions.ensure_for_execution.assert_awaited_once_with(
        execution_id="execution-1",
        workspace_id="ws-1",
        user_id="user-1",
    )
    assert execution_service.update_execution.await_args_list[-1].kwargs["status"] == "pending"


@pytest.mark.asyncio
async def test_launch_marks_execution_advisory():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock(
        return_value=FeatureExecutionAdvisory(
            feature_id="thesis_writing",
            code="literature_insufficient",
            message="文献不足",
            context={"current": 3, "recommended": 15},
        )
    )
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    execution_service.create_execution = AsyncMock(
        return_value=_execution_record("execution-2", feature_id="thesis_writing", workspace_type="thesis")
    )
    execution_service.update_execution = AsyncMock()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("thesis_writing"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                feature_id="thesis_writing",
                params={"action": "write_all"},
                launch_source="thread",
            )
        )

    assert result.execution_id == "execution-2"
    assert execution_service.update_execution.await_args_list[-1].kwargs["advisory_code"] == "literature_insufficient"


@pytest.mark.asyncio
async def test_launch_reuses_existing_execution_when_task_is_reused():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-1",
            feature_id="framework_outline",
            message="已有进行中的 框架与摘要 任务",
            reused_existing_task=True,
            execution_id="exec-existing",
        )
    )
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    execution_service.create_execution = AsyncMock(
        return_value=_execution_record("execution-new")
    )
    execution_service.cancel_execution = AsyncMock()
    execution_service.update_execution = AsyncMock()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("framework_outline"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                feature_id="framework_outline",
                params={},
                launch_source="thread",
            )
    )

    assert result.execution_id == "exec-existing"
    execution_service.cancel_execution.assert_awaited_once_with("execution-new")
    assert compute_sessions.ensure_for_execution.await_count == 1
    assert compute_sessions.ensure_for_execution.await_args.kwargs["execution_id"] == "execution-new"


@pytest.mark.asyncio
async def test_launch_rejects_unknown_feature_for_workspace_type():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=None,
    ):
        with pytest.raises(NotFoundError):
            await service.launch(
                FeatureLaunchCommand(
                    workspace_id="ws-1",
                    feature_id="thesis_writing",
                    launch_source="thread",
                )
            )

    execution_service.create_execution.assert_not_awaited()
    compute_sessions.ensure_for_execution.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_launch_missing_context_enters_awaiting_user_input():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock()
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    execution_service.create_execution = AsyncMock(
        return_value=_execution_record("exec-clarify", feature_id="deep_research", workspace_type="thesis")
    )
    execution_service.update_execution = AsyncMock()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("deep_research"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="开始深度调研",
            )
        )

    assert result.execution_id == "exec-clarify"
    assert isinstance(result.outcome, FeatureExecutionAdvisory)
    assert result.outcome.code == "missing_params"
    handler.execute.assert_not_awaited()
    assert execution_service.update_execution.await_args_list[-1].kwargs["status"] == "awaiting_user_input"


@pytest.mark.asyncio
async def test_resume_uses_existing_execution_and_merges_params():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-resume",
            feature_id="deep_research",
            message="Queued 深度调研",
        )
    )
    compute_sessions = _compute_sessions()
    execution_service = AsyncMock()
    execution_service.get_by_id = AsyncMock(
        return_value=_execution_record(
            "exec-existing",
            feature_id="deep_research",
            workspace_type="thesis",
            entry_skill_id="deep-research",
            params={"topic": "初始主题"},
        )
    )
    execution_service.update_execution = AsyncMock()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
        execution_service=execution_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("deep_research"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                execution_id="exec-existing",
                feature_id=None,
                params={"query": "补充检索词"},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="继续调研这个方向",
            )
        )

    assert result.execution_id == "exec-existing"
    assert isinstance(result.outcome, FeatureTaskSubmission)
    compute_sessions.ensure_for_execution.assert_awaited_once_with(
        execution_id="exec-existing",
        workspace_id="ws-1",
        user_id="user-1",
    )
    handler.execute.assert_awaited_once()
    call_args = handler.execute.await_args
    assert call_args.kwargs["execution_id"] == "exec-existing"
    merged_params = call_args.args[2]
    assert merged_params["topic"] == "初始主题"
    assert merged_params["query"] == "补充检索词"
