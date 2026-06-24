"""DataService conversation domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.dataservice.conversation_api import ConversationDataService
from src.dataservice.domains.conversation.block_protocol import blocks_from_message
from src.dataservice.domains.conversation.contracts import ConversationMessageCreateCommand
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage, ToolInvocationRecord
from src.dataservice.domains.conversation.service import DataServiceConversationService


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.execute = AsyncMock()
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    def add(self, value: Any) -> None:
        self.added.append(value)


def _thread_like() -> Any:
    return type(
        "ThreadLike",
        (),
        {
            "id": "thread-1",
            "user_id": "user-1",
            "workspace_id": "ws-1",
            "messages": [],
            "message_count": 0,
            "last_message_role": None,
            "last_message_preview": None,
            "updated_at": None,
        },
    )()


def test_blocks_from_message_normalizes_to_canonical_kinds() -> None:
    blocks = blocks_from_message(
        {
            "content": "fallback text",
            "blocks": [
                {"type": "reasoning", "title": "思考过程", "data": {"text": "thinking"}},
                {"kind": "status_line", "label": "running"},
                {
                    "kind": "tool_invocation",
                    "data": {
                        "tool": "launch_feature",
                        "args": {"feature_id": "outline"},
                        "tool_call_id": "call-1",
                    },
                },
                {
                    "kind": "tool_result",
                    "data": {
                        "tool": "launch_feature",
                        "status": "launched",
                        "execution_id": "exec-1",
                        "feature_id": "outline",
                    },
                },
                {"kind": "custom_legacy", "content": "legacy"},
            ],
        }
    )

    assert [block["kind"] for block in blocks] == [
        "thinking",
        "status_line",
        "tool_invocation",
        "tool_result",
        "text",
    ]
    assert blocks[0] == {"kind": "thinking", "content": "thinking"}
    assert blocks[2] == {
        "kind": "tool_invocation",
        "tool": "launch_feature",
        "input": {"feature_id": "outline"},
        "tool_call_id": "call-1",
    }
    assert blocks[3] == {
        "kind": "tool_result",
        "tool": "launch_feature",
        "status": "launched",
        "output": {
            "tool": "launch_feature",
            "status": "launched",
            "execution_id": "exec-1",
            "feature_id": "outline",
        },
        "execution_id": "exec-1",
        "feature_id": "outline",
    }
    assert all("legacy_kind" not in block for block in blocks)


@pytest.mark.asyncio
async def test_append_message_materializes_ordered_blocks_and_tool_record() -> None:
    session = FakeSession()
    service = DataServiceConversationService(session)  # type: ignore[arg-type]
    thread = SimpleNamespace(
        id="thread-1",
        message_count=0,
        last_message_role=None,
        last_message_preview=None,
        updated_at=None,
    )
    service.repository.lock_thread = AsyncMock()  # type: ignore[method-assign]
    service.repository.get_thread = AsyncMock(return_value=thread)  # type: ignore[method-assign]
    service.repository.next_message_sequence = AsyncMock(return_value=0)  # type: ignore[method-assign]

    message = await service.append_message(
        ConversationMessageCreateCommand(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            role="assistant",
            content="Done",
            timestamp=datetime(2026, 5, 21, tzinfo=UTC),
            sequence_index=0,
            blocks=[
                {"kind": "text", "content": "Working"},
                {"kind": "tool_invocation", "tool_name": "search", "input": {"q": "paper"}},
            ],
        )
    )

    assert isinstance(message, ThreadMessage)
    assert message.sequence_index == 0
    block_rows = [item for item in session.added if isinstance(item, MessageBlock)]
    assert [block.block_type for block in block_rows] == ["text", "tool_invocation"]
    assert [block.sequence_index for block in block_rows] == [0, 1]
    tool_rows = [item for item in session.added if isinstance(item, ToolInvocationRecord)]
    assert len(tool_rows) == 1
    assert tool_rows[0].tool_name == "search"
    assert thread.message_count == 1
    assert thread.last_message_role == "assistant"
    assert thread.last_message_preview == "Done"
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_conversation_public_api_replaces_thread_messages() -> None:
    session = FakeSession()
    api = ConversationDataService(session, autocommit=False)  # type: ignore[arg-type]
    thread = _thread_like()
    api._domain.repository.lock_thread = AsyncMock()  # type: ignore[attr-defined,method-assign] # noqa: SLF001
    api._domain.repository.get_thread = AsyncMock(return_value=thread)  # type: ignore[attr-defined,method-assign] # noqa: SLF001
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi", "blocks": [{"kind": "text", "content": "Hi"}]},
    ]

    await api.replace_thread_messages(thread, messages)

    assert session.execute.await_count == 1
    message_rows = [item for item in session.added if isinstance(item, ThreadMessage)]
    assert [row.sequence_index for row in message_rows] == [0, 1]
    block_rows = [item for item in session.added if isinstance(item, MessageBlock)]
    assert [row.sequence_index for row in block_rows] == [0, 0]
    assert session.flush.await_count == 3


@pytest.mark.asyncio
async def test_list_workspace_thread_summaries_projects_thread_rows() -> None:
    session = FakeSession()
    service = DataServiceConversationService(session, autocommit=False)  # type: ignore[arg-type]
    service.repository.list_workspace_threads = AsyncMock(
        return_value=[
            SimpleNamespace(
                id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                title="Research thread",
                model="gpt-x",
                skill="deep_research",
                message_count=2,
                last_message_preview="latest",
                last_message_role="assistant",
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
                updated_at=datetime(2026, 5, 21, tzinfo=UTC),
            )
        ]
    )

    summaries = await service.list_workspace_thread_summaries(
        workspace_id="ws-1",
        limit=10,
    )

    assert summaries[0].id == "thread-1"
    assert summaries[0].skill == "deep_research"
    assert summaries[0].last_message_preview == "latest"
    service.repository.list_workspace_threads.assert_awaited_once_with(
        workspace_id="ws-1",
        limit=10,
    )
