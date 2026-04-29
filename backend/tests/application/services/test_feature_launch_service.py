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


def _compute_sessions():
    service = AsyncMock()
    service.ensure_for_execution_session = AsyncMock(
        return_value=SimpleNamespace(id="compute-1")
    )
    return service


@pytest.mark.asyncio
async def test_launch_creates_execution_session_and_passes_id_to_handler():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-1",
            feature_id="framework_outline",
            message="Queued 框架与摘要",
        )
    )
    execution_sessions = AsyncMock()
    execution_sessions.create_session = AsyncMock(
        return_value=SimpleNamespace(id="exec-1")
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
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

    assert result.execution_session_id == "exec-1"
    handler.execute.assert_awaited_once()
    assert handler.execute.await_args.kwargs["execution_session_id"] == "exec-1"
    compute_sessions.ensure_for_execution_session.assert_awaited_once_with(
        execution_session_id="exec-1",
        workspace_id="ws-1",
        user_id="user-1",
    )
    execution_sessions.update_session_record.assert_awaited_once()
    assert execution_sessions.update_session_record.await_args.kwargs["status"] == "pending"
    assert execution_sessions.update_session_record.await_args.kwargs["primary_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_launch_marks_execution_session_advisory():
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
    execution_sessions = AsyncMock()
    execution_sessions.create_session = AsyncMock(
        return_value=SimpleNamespace(id="exec-2")
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
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

    assert result.execution_session_id == "exec-2"
    assert execution_sessions.update_session_record.await_args.kwargs["status"] == "advisory"
    assert execution_sessions.update_session_record.await_args.kwargs["advisory_code"] == "literature_insufficient"


@pytest.mark.asyncio
async def test_launch_reuses_existing_execution_session_when_task_is_reused():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-1",
            feature_id="framework_outline",
            message="已有进行中的 框架与摘要 任务",
            reused_existing_task=True,
        )
    )
    handler.task_service.get_task_status = AsyncMock(
        return_value={"task_id": "task-1", "execution_session_id": "exec-existing"}
    )
    execution_sessions = AsyncMock()
    execution_sessions.create_session = AsyncMock(
        return_value=SimpleNamespace(id="exec-new")
    )
    execution_sessions.delete_session = AsyncMock()
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
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

    assert result.execution_session_id == "exec-existing"
    execution_sessions.delete_session.assert_awaited_once_with("exec-new")
    execution_sessions.update_session_record.assert_not_awaited()
    assert compute_sessions.ensure_for_execution_session.await_count == 2
    assert compute_sessions.ensure_for_execution_session.await_args.kwargs["execution_session_id"] == "exec-existing"


@pytest.mark.asyncio
async def test_launch_rejects_unknown_feature_for_workspace_type():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("sci"))
    execution_sessions = AsyncMock()
    compute_sessions = _compute_sessions()
    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
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

    execution_sessions.create_session.assert_not_awaited()
    compute_sessions.ensure_for_execution_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_launch_missing_context_enters_awaiting_user_input():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock()
    execution_sessions = AsyncMock()
    execution_sessions.create_session = AsyncMock(
        return_value=SimpleNamespace(id="exec-clarify")
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
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

    assert result.execution_session_id == "exec-clarify"
    assert isinstance(result.outcome, FeatureExecutionAdvisory)
    assert result.outcome.code == "missing_params"
    handler.execute.assert_not_awaited()
    assert execution_sessions.update_session_record.await_args.kwargs["status"] == "awaiting_user_input"


@pytest.mark.asyncio
async def test_resume_uses_existing_execution_session_and_merges_params():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-resume",
            feature_id="deep_research",
            message="Queued 深度调研",
        )
    )
    execution_sessions = AsyncMock()
    execution_sessions.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="exec-existing",
            user_id="user-1",
            workspace_id="ws-1",
            workspace_type="thesis",
            feature_id="deep_research",
            thread_id="thread-1",
            entry_skill_id="deep-research",
            params={"topic": "初始主题"},
        )
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("deep_research"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                execution_session_id="exec-existing",
                feature_id=None,
                params={"query": "补充检索词"},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="继续调研这个方向",
            )
        )

    assert result.execution_session_id == "exec-existing"
    assert isinstance(result.outcome, FeatureTaskSubmission)
    compute_sessions.ensure_for_execution_session.assert_awaited_once_with(
        execution_session_id="exec-existing",
        workspace_id="ws-1",
        user_id="user-1",
    )
    handler.execute.assert_awaited_once()
    call_args = handler.execute.await_args
    assert call_args.kwargs["execution_session_id"] == "exec-existing"
    merged_params = call_args.args[2]
    assert merged_params["topic"] == "初始主题"
    assert merged_params["query"] == "补充检索词"


@pytest.mark.asyncio
async def test_resume_hydrates_missing_required_params_from_launch_message():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-resume",
            feature_id="deep_research",
            message="Queued 深度调研",
        )
    )
    execution_sessions = AsyncMock()
    execution_sessions.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="exec-existing",
            user_id="user-1",
            workspace_id="ws-1",
            workspace_type="thesis",
            feature_id="deep_research",
            thread_id="thread-1",
            entry_skill_id="deep-research",
            params={},
        )
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("deep_research"),
    ):
        result = await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                execution_session_id="exec-existing",
                feature_id=None,
                params={},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="研究主题是多模态医学影像分割",
            )
        )

    assert result.execution_session_id == "exec-existing"
    assert isinstance(result.outcome, FeatureTaskSubmission)
    handler.execute.assert_awaited_once()
    merged_params = handler.execute.await_args.args[2]
    assert merged_params["topic"] == "研究主题是多模态医学影像分割"


@pytest.mark.asyncio
async def test_resume_submission_clears_advisory_and_next_actions():
    handler = AsyncMock()
    handler.workspace_service.get = AsyncMock(return_value=_workspace("thesis"))
    handler.execute = AsyncMock(
        return_value=FeatureTaskSubmission(
            task_id="task-resume",
            feature_id="deep_research",
            message="Queued 深度调研",
        )
    )
    execution_sessions = AsyncMock()
    execution_sessions.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="exec-existing",
            user_id="user-1",
            workspace_id="ws-1",
            workspace_type="thesis",
            feature_id="deep_research",
            thread_id="thread-1",
            entry_skill_id="deep-research",
            params={"topic": "初始主题"},
            advisory_code="missing_params",
            next_actions=[{"kind": "user_input_required"}],
            last_error=None,
        )
    )
    execution_sessions.update_session_record = AsyncMock()
    compute_sessions = _compute_sessions()

    service = FeatureIngressService(
        actor_id="user-1",
        feature_submission_service=handler,
        execution_session_service=execution_sessions,
        compute_session_service=compute_sessions,
        workspace_service=handler.workspace_service,
    )

    with patch(
        "src.application.services.feature_launch_service.get_workspace_feature",
        return_value=_feature("deep_research"),
    ):
        await service.launch(
            FeatureLaunchCommand(
                workspace_id="ws-1",
                execution_session_id="exec-existing",
                feature_id=None,
                params={"query": "补充检索词"},
                thread_id="thread-1",
                launch_source="thread",
                launch_message="继续调研这个方向",
            )
        )

    finalize_call = execution_sessions.update_session_record.await_args_list[-1]
    assert finalize_call.kwargs["status"] == "pending"
    assert finalize_call.kwargs["next_actions"] == []
    assert finalize_call.kwargs["advisory_code"] is None
    assert finalize_call.kwargs["last_error"] is None
