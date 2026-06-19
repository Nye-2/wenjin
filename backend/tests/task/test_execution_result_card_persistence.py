"""Tests for execution completion result_card persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.tasks.execution import (
    _persist_result_card_for_execution,
    _resolve_execution_workspace_type,
    _result_card_data_from_task_report,
)


def test_result_card_data_from_task_report_preserves_outputs_and_reviews() -> None:
    task_report = {
        "execution_id": "exec-1",
        "capability_id": "sci_literature_positioning",
        "status": "completed",
        "narrative": "完成文献定位。",
        "duration_seconds": 12,
        "preview_item_id": "team.1.research_scout_v1.1.output",
        "outputs": [
            {
                "id": "out-1",
                "kind": "document",
                "preview": "定位报告",
                "default_checked": True,
                "data": {"name": "文献定位与创新点.md"},
            }
        ],
        "review_items": [
            {
                "id": "review-1",
                "kind": "prism_file_change",
                "status": "pending",
            }
        ],
    }

    data = _result_card_data_from_task_report("fallback-exec", task_report)

    assert data["execution_id"] == "exec-1"
    assert data["capability_name"] == "sci_literature_positioning"
    assert data["status"] == "completed"
    assert data["narrative"] == "完成文献定位。"
    assert data["duration_seconds"] == 12
    assert data["preview_item_id"] == "team.1.research_scout_v1.1.output"
    assert data["outputs"] == [
        {
            "id": "out-1",
            "kind": "document",
            "preview": "定位报告",
            "default_checked": True,
            "data": {"name": "文献定位与创新点.md"},
        }
    ]
    assert data["review_items"] == [
        {
            "id": "review-1",
            "kind": "prism_file_change",
            "status": "pending",
        }
    ]
    assert data["errors"] == []


def test_result_card_data_from_failed_partial_outputs_are_not_prechecked() -> None:
    task_report = {
        "execution_id": "exec-partial",
        "capability_id": "sci_literature_positioning",
        "status": "failed_partial",
        "narrative": "未能完成文献定位。",
        "outputs": [
            {
                "id": "paper-1",
                "kind": "library_item",
                "preview": "Paper A",
                "default_checked": True,
                "data": {"title": "Paper A", "authors": ["Smith"]},
            }
        ],
    }

    data = _result_card_data_from_task_report("fallback-exec", task_report)

    assert data["status"] == "failed_partial"
    assert data["outputs"][0]["default_checked"] is False


@pytest.mark.asyncio
async def test_resolve_execution_workspace_type_uses_dataservice_projection() -> None:
    dataservice = SimpleNamespace(
        get_workspace=AsyncMock(return_value=SimpleNamespace(workspace_type="sci")),
    )

    workspace_type = await _resolve_execution_workspace_type(dataservice, "ws-1")

    assert workspace_type == "sci"
    dataservice.get_workspace.assert_awaited_once_with("ws-1")


@pytest.mark.asyncio
async def test_resolve_execution_workspace_type_rejects_missing_type() -> None:
    dataservice = SimpleNamespace(
        get_workspace=AsyncMock(return_value=SimpleNamespace(workspace_type=None)),
    )

    with pytest.raises(ValueError, match="workspace type is not configured"):
        await _resolve_execution_workspace_type(dataservice, "ws-1")


@pytest.mark.asyncio
async def test_persist_result_card_for_execution_appends_once() -> None:
    thread = SimpleNamespace(id="thread-1", user_id="user-1", workspace_id="ws-1", message_count=0)
    dataservice = SimpleNamespace(
        get_conversation_thread=AsyncMock(return_value=thread),
        list_conversation_messages=AsyncMock(return_value=[]),
        append_conversation_message=AsyncMock(),
    )

    execution = SimpleNamespace(
        id="exec-1",
        thread_id="thread-1",
        result={
            "task_report": {
                "execution_id": "exec-1",
                "capability_id": "sci_literature_positioning",
                "status": "completed",
                "narrative": "完成 文献定位与创新点，共执行 3 个节点。",
                "outputs": [
                    {
                        "id": "out-1",
                        "kind": "document",
                        "preview": "定位报告",
                        "data": {"name": "文献定位与创新点.md"},
                    }
                ],
            }
        },
    )

    await _persist_result_card_for_execution(dataservice, execution)

    dataservice.append_conversation_message.assert_awaited_once()
    args = dataservice.append_conversation_message.await_args.args
    assert args[0] == "thread-1"
    command = args[1]
    assert command.thread_id == "thread-1"
    assert command.user_id == "user-1"
    assert command.workspace_id == "ws-1"
    assert command.role == "assistant"
    assert command.content == "完成 文献定位与创新点，共执行 3 个节点。"
    assert command.metadata == {
        "source": "execution_completion",
        "execution_id": "exec-1",
    }
    assert command.blocks == [
        {
            "kind": "result_card",
            "data": {
                "execution_id": "exec-1",
                "capability_name": "sci_literature_positioning",
                "status": "completed",
                "outputs": [
                    {
                        "id": "out-1",
                        "kind": "document",
                        "preview": "定位报告",
                        "default_checked": True,
                        "data": {"name": "文献定位与创新点.md"},
                    }
                ],
                "review_items": None,
                "narrative": "完成 文献定位与创新点，共执行 3 个节点。",
                "duration_seconds": None,
                "errors": [],
            },
        }
    ]

    dataservice.list_conversation_messages.return_value = [
        SimpleNamespace(
            role="assistant",
            blocks=[
                SimpleNamespace(
                    payload_json={
                        "kind": "result_card",
                        "data": {"execution_id": "exec-1"},
                    }
                )
            ],
        )
    ]

    await _persist_result_card_for_execution(dataservice, execution)

    dataservice.append_conversation_message.assert_awaited_once()
