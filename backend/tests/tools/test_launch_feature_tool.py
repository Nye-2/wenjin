"""Tests for the `launch_feature` builtin tool — v2 execution pipeline."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.application.services.feature_launch_context import (
    extract_capability_minimum_context,
    resolve_missing_context_fields,
)
from src.dataservice_client.errors import DataServiceClientError
from src.tools.builtins import launch_feature_tool


@dataclass
class _StubExecution:
    id: str


def _capability(capability_id: str = "idea_to_thesis_manuscript") -> SimpleNamespace:
    is_sci_manuscript = capability_id == "research_question_to_paper"
    routing = {}
    definition_json = {}
    display_name = "Idea To Thesis Manuscript"
    if is_sci_manuscript:
        display_name = "问题到 SCI 初稿"
        routing = {"minimum_context": {"topic": "required"}}
    elif capability_id == "thesis_research_pack":
        display_name = "Thesis Research Pack"
        routing = {"minimum_context": {"goal_or_topic": "required"}}
    elif capability_id == "sci_literature_positioning":
        display_name = "文献定位与创新点"
        routing = {
            "minimum_context": {"existing_materials_summary": "required"},
            "clarification": {"ask_when_missing": "请发已有材料摘要。"},
        }
    elif capability_id == "definition_json_only_clarification":
        display_name = "Definition JSON Routing"
        definition_json = {
            "routing": {
                "minimum_context": {
                    "existing_materials_summary": "required",
                    "target_journal": "required",
                },
                "clarification": {
                    "ask_when_missing": {
                        "existing_materials_summary": "请先补充已有材料摘要。",
                        "target_journal": "请说明目标期刊。",
                    },
                },
            },
        }
    if routing:
        definition_json = {"routing": routing}
    return SimpleNamespace(
        id=capability_id,
        workspace_type="thesis",
        schema_version="capability.v2",
        enabled=True,
        display_name=display_name,
        description="",
        intent_description="",
        trigger_phrases=[],
        required_decisions=[],
        brief_schema={},
        graph_template={},
        ui_meta={},
        runtime={},
        dashboard_meta={},
        routing=routing,
        definition_json=definition_json,
        notes=None,
        checksum=None,
        source_path=None,
        created_at=None,
        updated_at=None,
    )


def test_missing_context_uses_capability_minimum_context_not_hardcoded_fallback():
    cap = SimpleNamespace(
        routing={
            "minimum_context": {"existing_materials_summary": "required"},
            "clarification": {"ask_when_missing": "请发已有材料摘要。"},
        },
        definition_json={},
    )

    missing = resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={"topic": "LLM agents"},
        launch_source="tool",
        minimum_context=extract_capability_minimum_context(cap),
    )

    assert missing == ["existing_materials_summary"]


def test_missing_context_without_capability_minimum_context_has_no_static_fallback():
    missing = resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={},
        launch_source="tool",
        minimum_context=None,
    )

    assert missing == []


class _FakeDataServiceClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_workspace(self, workspace_id: str):
        return SimpleNamespace(id=workspace_id, workspace_type="thesis")

    async def get_catalog_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = True,
    ):
        if capability_id == "legacy_missing":
            return None
        capability = _capability(capability_id)
        capability.workspace_type = workspace_type
        return capability

    async def list_catalog_capabilities(self, *, workspace_type: str, enabled_only: bool = True):
        return [_capability("idea_to_thesis_manuscript"), _capability("thesis_research_pack")]

    async def get_credit_consumed_tokens(
        self,
        *,
        user_id: str,
        consume_type: str,
        metadata_type: str | None = None,
    ) -> int:
        return 0

    async def get_credit_balance(self, user_id: str) -> int | None:
        return 10

    async def get_credit_summary(self, user_id: str):
        return SimpleNamespace(
            model_dump=lambda: {
                "credits": 10,
                "reserved_credits": 0,
                "spendable_credits": 10,
            }
        )

    async def create_credit_reservation(self, command):
        return SimpleNamespace(
            id="reservation-1",
            status="reserved",
            reserved_credits=command.reserved_credits,
        )

    async def release_credit_reservation(self, reservation_id: str, *, reason: str | None = None):
        return SimpleNamespace(
            id=reservation_id,
            status="released",
            release_reason=reason,
        )


@pytest.fixture(autouse=True)
def _patch_dataservice_client(monkeypatch: pytest.MonkeyPatch):
    def _factory():
        return _FakeDataServiceClient()

    monkeypatch.setattr("src.dataservice_client.provider.dataservice_client", _factory)
    monkeypatch.setattr("src.services.credit_service.dataservice_client", _factory)
    monkeypatch.setattr("src.services.workspace_skill_labels.dataservice_client", _factory)


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
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-1")
    fake_service.update_execution = AsyncMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.workspace_events.publish_workspace_event", fake_publish), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
                "skill_id": "manuscript-writer",
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
    assert result["feature_id"] == "idea_to_thesis_manuscript"
    fake_service.create_execution.assert_awaited_once()
    create_kwargs = fake_service.create_execution.await_args.kwargs
    assert create_kwargs["execution_type"] == "feature"
    assert create_kwargs["thread_id"] == "th-1"
    assert create_kwargs["display_name"] == "Idea To Thesis Manuscript"
    assert create_kwargs["commit"] is False
    fake_celery_app.send_task.assert_called_once_with(
        "src.task.tasks.execute_execution",
        args=["exec-1"],
        queue="long_running",
    )
    fake_service.update_execution.assert_awaited_with(
        "exec-1",
        dispatch_mode="celery_worker",
        worker_task_id="worker-task-1",
    )


@pytest.mark.asyncio
async def test_launch_feature_reuses_execution_for_same_user_message():
    """Repeated tool calls for one chat turn should reuse the first execution."""
    dispatched: list[str] = []
    executions: list[SimpleNamespace] = []

    async def _list_executions(
        *,
        workspace_id: str,
        status: list[str] | None = None,
        limit: int | None = None,
    ):
        if status:
            return executions
        if limit:
            return executions
        return []

    async def _create_execution(**kwargs):
        execution = SimpleNamespace(id="exec-1", **kwargs)
        executions.append(execution)
        return execution

    async def _update_execution(execution_id: str, **kwargs):
        execution = executions[0]
        for key, value in kwargs.items():
            setattr(execution, key, value)
        return execution

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(side_effect=_list_executions)
    fake_service.create_execution = AsyncMock(side_effect=_create_execution)
    fake_service.update_execution = AsyncMock(side_effect=_update_execution)
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=120)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-1", reserved_credits=120, status="reserved")
    )
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()

    def _send_task(name: str, args: list[str], **kwargs):
        dispatched.append(args[0])
        return SimpleNamespace(id=f"worker-task-{len(dispatched)}")

    fake_celery_app.send_task.side_effect = _send_task

    config = {
        "configurable": {
            "workspace_id": "ws-1",
            "thread_id": "thread-1",
            "user_id": "user-1",
            "user_message_id": "msg-1",
            "launch_idempotency_key": "launch_feature:thread-1:msg-1",
        }
    }

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        first = await launch_feature_tool.ainvoke(
            {"feature_id": "idea_to_thesis_manuscript", "params": {"topic": "LLM agents"}},
            config=config,
        )
        second = await launch_feature_tool.ainvoke(
            {"feature_id": "idea_to_thesis_manuscript", "params": {"topic": "LLM agents"}},
            config=config,
        )

    assert first["status"] == "launched"
    assert second["status"] == "launched"
    assert second["execution_id"] == first["execution_id"]
    assert dispatched == [first["execution_id"]]


@pytest.mark.asyncio
async def test_launch_feature_creates_credit_reservation_before_dispatch():
    fake_execution = _StubExecution(id="exec-1")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=120)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-1", reserved_credits=120, status="reserved")
    )
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-1")

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
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
    fake_credit_service.estimate_feature_reservation_credits.assert_awaited_once_with(
        feature_id="idea_to_thesis_manuscript",
        workspace_type="thesis",
    )
    fake_credit_service.reserve_for_feature_execution.assert_awaited_once_with(
        user_id="user-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        estimated_credits=120,
        expires_at=ANY,
        idempotency_key="feature_execution:exec-1",
        metadata={
            "feature_id": "idea_to_thesis_manuscript",
            "workspace_type": "thesis",
            "source": "launch_feature",
        },
    )
    reservation_call = fake_credit_service.reserve_for_feature_execution.await_args.kwargs
    assert reservation_call["expires_at"] is not None
    reservation_updates = [
        call.kwargs for call in fake_service.update_execution.await_args_list
        if call.kwargs.get("params")
    ]
    assert reservation_updates[0]["params"]["billing"]["credit_reservation_id"] == "reservation-1"


@pytest.mark.asyncio
async def test_launch_feature_uses_selected_skill_from_runtime_config_when_tool_args_omit_it():
    """Chat-selected skill should survive into the launched execution."""
    fake_execution = _StubExecution(id="exec-2")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-2")
    fake_service.update_execution = AsyncMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                }
            },
        )

    assert result["status"] == "launched"
    fake_service.create_execution.assert_awaited_once()
    create_kwargs = fake_service.create_execution.await_args.kwargs
    assert create_kwargs["entry_skill_id"] == "manuscript-writer"


@pytest.mark.asyncio
async def test_launch_feature_rejects_workbench_picker_without_required_topic():
    """A direct workbench capability click must not create an empty execution."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_service.update_execution = AsyncMock()
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()
    prompt = "\n".join(
        [
            "我想使用「问题到 SCI 初稿」能力。",
            "请先确认启动所需的具体研究主题、材料或目标；信息足够时再组织研究团队。",
        ]
    )

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "research_question_to_paper",
                "params": {"topic": prompt, "raw_message": prompt},
            },
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
    assert "问题到 SCI 初稿" in result["detail"]
    assert "研究主题" in result["detail"]
    fake_service.create_execution.assert_not_called()
    fake_service.update_execution.assert_not_called()
    fake_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_missing_context_uses_routing_clarification_copy():
    """Missing-context advisory should reuse capability routing copy when available."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_service.update_execution = AsyncMock()
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "sci_literature_positioning",
                "params": {"topic": "LLM agents"},
            },
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
    assert result["detail"] == "请发已有材料摘要。"
    assert result["context"]["prompt"] == "请发已有材料摘要。"
    assert result["context"]["missing_fields"] == ["existing_materials_summary"]
    fake_service.create_execution.assert_not_called()
    fake_service.update_execution.assert_not_called()
    fake_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_uses_definition_json_per_field_clarification_copy():
    """Per-field clarification prompts from definition_json.routing should use first missing field."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_service.update_execution = AsyncMock()
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "definition_json_only_clarification",
                "params": {"topic": "LLM agents"},
            },
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
    assert result["detail"] == "请先补充已有材料摘要。"
    assert result["context"]["prompt"] == "请先补充已有材料摘要。"
    assert result["context"]["missing_fields"] == [
        "existing_materials_summary",
        "target_journal",
    ]
    fake_service.create_execution.assert_not_called()
    fake_service.update_execution.assert_not_called()
    fake_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_merges_runtime_launch_params_when_tool_args_are_partial():
    """Workspace entry seeds should survive even if the model omits them."""
    fake_execution = _StubExecution(id="exec-3")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-3")
    fake_service.update_execution = AsyncMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                    "launch_feature_params": {
                        "source_artifact_id": "artifact-2",
                        "context_artifact_ids": ["artifact-2", "artifact-3"],
                        "paper_title": "会被显式参数覆盖的旧标题",
                    },
                }
            },
        )

    assert result["status"] == "launched"
    fake_service.create_execution.assert_awaited_once()
    create_kwargs = fake_service.create_execution.await_args.kwargs
    assert create_kwargs["params"]["brief"]["brief"] == {
        "paper_title": "联邦学习结合大模型微调",
        "source_artifact_id": "artifact-2",
        "context_artifact_ids": ["artifact-2", "artifact-3"],
    }


@pytest.mark.asyncio
async def test_launch_feature_reuses_execution_id_from_runtime_config_for_resume():
    """Resume flows should dispatch the existing execution instead of creating a new one."""
    fake_execution = _StubExecution(id="exec-9")
    fake_execution.workspace_id = "ws-1"  # type: ignore[attr-defined]
    fake_execution.user_id = "user-1"  # type: ignore[attr-defined]
    fake_execution.feature_id = "idea_to_thesis_manuscript"  # type: ignore[attr-defined]
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock(return_value=fake_execution)
    fake_service.create_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=120)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-1", reserved_credits=120, status="reserved")
    )
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-9")

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                    "execution_id": "exec-9",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["execution_id"] == "exec-9"
    fake_service.create_execution.assert_not_called()
    fake_credit_service.reserve_for_feature_execution.assert_awaited_once()
    reservation_call = fake_credit_service.reserve_for_feature_execution.await_args.kwargs
    assert reservation_call["idempotency_key"] == "feature_execution:exec-9"
    assert fake_service.update_execution.await_count == 2
    update_kwargs = fake_service.update_execution.await_args_list[0].kwargs
    assert update_kwargs["status"] == "pending"
    assert update_kwargs["thread_id"] == "th-1"
    assert update_kwargs["entry_skill_id"] == "manuscript-writer"
    assert update_kwargs["params"]["brief"]["capability_id"] == "idea_to_thesis_manuscript"
    assert update_kwargs["params"]["billing"]["credit_reservation_id"] == "reservation-1"
    assert update_kwargs["params"]["billing"]["reservation_status"] == "reserved"
    dispatch_kwargs = fake_service.update_execution.await_args_list[1].kwargs
    assert dispatch_kwargs == {
        "dispatch_mode": "celery_worker",
        "worker_task_id": "worker-task-9",
    }


@pytest.mark.asyncio
async def test_launch_feature_resume_keeps_existing_credit_reservation():
    """Resume flows must not create a second credit reservation for the same execution."""
    fake_execution = _StubExecution(id="exec-9")
    fake_execution.workspace_id = "ws-1"  # type: ignore[attr-defined]
    fake_execution.user_id = "user-1"  # type: ignore[attr-defined]
    fake_execution.feature_id = "idea_to_thesis_manuscript"  # type: ignore[attr-defined]
    fake_execution.params = {  # type: ignore[attr-defined]
        "brief": {"capability_id": "idea_to_thesis_manuscript"},
        "billing": {
            "credit_reservation_id": "reservation-existing",
            "reserved_credits": 77,
        },
    }

    async def _update_execution(execution_id: str, **kwargs):
        if "params" in kwargs:
            fake_execution.params = kwargs["params"]  # type: ignore[attr-defined]
        return fake_execution

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock(side_effect=_update_execution)
    fake_service.create_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=33)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-existing", reserved_credits=77, status="reserved")
    )
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.return_value = SimpleNamespace(id="worker-task-9")

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                    "execution_id": "exec-9",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["execution_id"] == "exec-9"
    fake_service.create_execution.assert_not_called()
    fake_credit_service.estimate_feature_reservation_credits.assert_awaited_once()
    fake_credit_service.reserve_for_feature_execution.assert_awaited_once()
    reservation_call = fake_credit_service.reserve_for_feature_execution.await_args.kwargs
    assert reservation_call["idempotency_key"] == "feature_execution:exec-9"
    assert fake_service.update_execution.await_count == 2
    resume_update = fake_service.update_execution.await_args_list[0].kwargs
    assert resume_update["params"]["billing"] == {
        "credit_reservation_id": "reservation-existing",
        "reserved_credits": 77,
        "reservation_status": "reserved",
    }
    dispatch_update = fake_service.update_execution.await_args_list[1].kwargs
    assert dispatch_update == {
        "dispatch_mode": "celery_worker",
        "worker_task_id": "worker-task-9",
    }


@pytest.mark.asyncio
async def test_launch_feature_resume_rejects_terminal_credit_reservation():
    """Resume should not dispatch work when the canonical reservation is no longer active."""
    fake_execution = _StubExecution(id="exec-9")
    fake_execution.workspace_id = "ws-1"  # type: ignore[attr-defined]
    fake_execution.user_id = "user-1"  # type: ignore[attr-defined]
    fake_execution.feature_id = "idea_to_thesis_manuscript"  # type: ignore[attr-defined]
    fake_execution.params = {  # type: ignore[attr-defined]
        "brief": {"capability_id": "idea_to_thesis_manuscript"},
        "billing": {
            "credit_reservation_id": "reservation-released",
            "reserved_credits": 77,
            "reservation_status": "released",
        },
    }

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock(return_value=fake_execution)
    fake_service.complete_execution = AsyncMock()
    fake_service.create_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=33)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-released", reserved_credits=77, status="released")
    )
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                    "execution_id": "exec-9",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "execution_reservation_unavailable"
    fake_service.create_execution.assert_not_called()
    fake_service.update_execution.assert_not_called()
    fake_service.complete_execution.assert_awaited_once()
    fake_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_rejects_resume_execution_id_from_another_workspace():
    """Resume must not mutate executions outside the current workspace/user scope."""
    foreign_execution = MagicMock()
    foreign_execution.id = "exec-foreign"
    foreign_execution.workspace_id = "ws-2"
    foreign_execution.user_id = "user-2"
    foreign_execution.feature_id = "idea_to_thesis_manuscript"

    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.get_by_id = AsyncMock(return_value=foreign_execution)
    fake_service.update_execution = AsyncMock()
    fake_service.create_execution = AsyncMock()
    fake_celery = MagicMock()
    fake_celery.enabled = True
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                    "selected_skill": "manuscript-writer",
                    "execution_id": "exec-foreign",
                }
            },
        )

    assert result["status"] == "error"
    assert result["code"] == "unknown_execution"
    assert result["execution_id"] == "exec-foreign"
    fake_service.update_execution.assert_not_called()
    fake_service.create_execution.assert_not_called()
    fake_celery_app.send_task.assert_not_called()


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
        return_value=[_ActiveExecution(id="exec-0", feature_id="research_question_to_paper", progress=50)]
    )

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "thesis_research_pack", "params": {}},
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
            {"feature_id": "idea_to_thesis_manuscript", "params": {}},
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
async def test_launch_feature_blocks_when_feature_credits_are_exhausted():
    """Feature launches should not enqueue compute once feature billing denies admission."""
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=False)
    fake_credit_service.get_feature_billing_policy.return_value = SimpleNamespace(
        free_tokens=0,
        tokens_per_credit=10000,
    )
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "idea_to_thesis_manuscript", "params": {}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "advisory"
    assert result["code"] == "feature_credits_required"
    fake_service.create_execution.assert_not_called()
    fake_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_launch_feature_marks_execution_failed_when_reservation_is_denied():
    """A failed credit reservation must not leave a pending execution locking the lead."""
    fake_execution = _StubExecution(id="exec-denied")
    fake_service = MagicMock()
    fake_service.list_executions = AsyncMock(return_value=[])
    fake_service.create_execution = AsyncMock(return_value=fake_execution)
    fake_service.update_execution = AsyncMock()
    fake_service.complete_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=120)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        side_effect=DataServiceClientError("insufficient spendable credits", status_code=402)
    )
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "idea_to_thesis_manuscript",
                "params": {"paper_title": "联邦学习结合大模型微调"},
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "advisory"
    assert result["code"] == "feature_credits_required"
    complete_call = fake_service.complete_execution.await_args
    assert complete_call.args[0] == "exec-denied"
    assert complete_call.kwargs["status"] == "failed"
    assert "积分" in complete_call.kwargs["result_summary"]
    fake_celery_app.send_task.assert_not_called()


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
            {"feature_id": "thesis_research_pack", "params": {}},
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
    fake_service.update_execution = AsyncMock()
    fake_service.complete_execution = AsyncMock()
    fake_credit_service = MagicMock()
    fake_credit_service.can_start_feature_task = AsyncMock(return_value=True)
    fake_credit_service.estimate_feature_reservation_credits = AsyncMock(return_value=100)
    fake_credit_service.reserve_for_feature_execution = AsyncMock(
        return_value=SimpleNamespace(id="reservation-1", reserved_credits=100, status="reserved")
    )
    fake_credit_service.release_reservation = AsyncMock()
    fake_celery = MagicMock(enabled=True)
    fake_celery_app = MagicMock()
    fake_celery_app.send_task.side_effect = RuntimeError("queue down")

    with patch("src.database.get_db_session", _fake_db_session), \
         patch("src.services.execution_service.ExecutionService", return_value=fake_service), \
         patch("src.services.credit_service.CreditService", return_value=fake_credit_service), \
         patch("src.config.app_config.celery_settings", fake_celery), \
         patch("src.task.celery_app.celery_app", fake_celery_app):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "idea_to_thesis_manuscript", "params": {}},
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
    fake_credit_service.release_reservation.assert_awaited_once_with(
        "reservation-1",
        reason="执行队列派发失败释放预留积分",
    )


@pytest.mark.asyncio
async def test_launch_feature_requires_workspace_in_config():
    """Tool fails fast if config lacks workspace_id (caller bug)."""
    with pytest.raises(ValueError, match="workspace_id"):
        await launch_feature_tool.ainvoke(
            {"feature_id": "idea_to_thesis_manuscript", "params": {}},
            config={"configurable": {"thread_id": "th-1", "user_id": "u-1"}},
        )
