"""Tests for ThreadService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dataservice_client.contracts.conversation import (
    ConversationMessagePayload,
    ConversationThreadPayload,
)
from src.models.router import InvalidRequestedModelError
from src.services.thread_service import ThreadAccessError, ThreadService


@pytest.fixture
def mock_db_session():
    """Create a mocked async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def service():
    """Create ThreadService instance."""
    return ThreadService(dataservice=_FakeConversationDataService())


@pytest.fixture
def fake_dataservice(service):
    return service._dataservice  # noqa: SLF001


@pytest.fixture(autouse=True)
def _patch_workspace_type_lookup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "src.services.thread_service.list_workspace_types",
        AsyncMock(return_value={"ws-1": "thesis", "ws-2": "thesis"}),
    )


class _FakeConversationDataService:
    def __init__(self) -> None:
        self.threads: dict[str, ConversationThreadPayload] = {}
        self.messages: dict[str, list[dict]] = {}
        self._next_thread_id = 1
        self.create_conversation_thread = AsyncMock(side_effect=self._create_thread)
        self.get_conversation_thread = AsyncMock(side_effect=self._get_thread)
        self.get_latest_workspace_conversation_thread = AsyncMock(
            side_effect=self._get_latest_workspace_thread
        )
        self.update_conversation_thread = AsyncMock(side_effect=self._update_thread)
        self.lock_conversation_thread = AsyncMock(return_value=None)
        self.append_conversation_message = AsyncMock(side_effect=self._append_message)
        self.rebuild_conversation_messages = AsyncMock(side_effect=self._rebuild_messages)
        self.list_conversation_messages = AsyncMock(side_effect=self._list_messages)
        self.list_conversation_threads = AsyncMock(side_effect=self._list_threads)
        self.delete_conversation_thread = AsyncMock(side_effect=self._delete_thread)

    async def _create_thread(self, command):
        thread = ConversationThreadPayload(
            id=f"thread-{self._next_thread_id}",
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            title=command.title,
            model=command.model,
            skill=command.skill,
            message_count=0,
            created_at=command.created_at,
            updated_at=command.updated_at,
        )
        self._next_thread_id += 1
        self.threads[thread.id] = thread
        return thread

    async def _get_thread(self, thread_id: str):
        return self.threads.get(thread_id)

    async def _get_latest_workspace_thread(self, *, user_id: str, workspace_id: str):
        for thread in reversed(list(self.threads.values())):
            if thread.user_id == user_id and thread.workspace_id == workspace_id:
                return thread
        return None

    async def _update_thread(self, thread_id: str, command):
        thread = self.threads.get(thread_id)
        if thread is None:
            return None
        updates = command.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(thread, key, value)
        return thread

    async def _append_message(self, thread_id: str, command):
        messages = self.messages.setdefault(thread_id, [])
        sequence_index = len(messages)
        messages.append(
            {
                "role": command.role,
                "content": command.content,
                "timestamp": command.timestamp.isoformat() if command.timestamp else None,
                "metadata": dict(command.metadata or {}),
                "blocks": list(command.blocks or []),
            }
        )
        return ConversationMessagePayload(
            id=f"msg-{sequence_index}",
            thread_id=thread_id,
            user_id=self.threads[thread_id].user_id,
            workspace_id=self.threads[thread_id].workspace_id,
            role=command.role,
            content=command.content,
            sequence_index=sequence_index,
            timestamp=command.timestamp,
            metadata_json=dict(command.metadata or {}),
            blocks=[],
        )

    async def _rebuild_messages(self, thread_id: str, command):
        self.messages[thread_id] = list(command.messages)
        return None

    async def _list_messages(self, thread_id: str):
        return [
            ConversationMessagePayload(
                id=f"msg-{index}",
                thread_id=thread_id,
                user_id=self.threads[thread_id].user_id,
                workspace_id=self.threads[thread_id].workspace_id,
                role=str(message.get("role") or ""),
                content=str(message.get("content") or ""),
                sequence_index=index,
                metadata_json=dict(message.get("metadata") or {}),
                blocks=[],
            )
            for index, message in enumerate(self.messages.get(thread_id, []))
        ]

    async def _list_threads(self, *, user_id: str, workspace_id: str | None = None, limit: int = 20):
        threads = [
            thread
            for thread in self.threads.values()
            if thread.user_id == user_id
            and (workspace_id is None or thread.workspace_id == workspace_id)
        ]
        return threads[:limit]

    async def _delete_thread(self, *, thread_id: str, user_id: str):
        thread = self.threads.get(thread_id)
        if thread is None or thread.user_id != user_id:
            return False
        del self.threads[thread_id]
        self.messages.pop(thread_id, None)
        return True


def _make_thread(
    *,
    user_id: str = "user-1",
    workspace_id: str | None = None,
    title: str | None = None,
    skill: str | None = None,
) -> ConversationThreadPayload:
    return ConversationThreadPayload(
        id="thread-1",
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        model="gpt-4o",
        skill=skill,
        message_count=0,
        last_message_preview=None,
        last_message_role=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _store_thread(service: ThreadService, thread: ConversationThreadPayload) -> None:
    service._dataservice.threads[str(thread.id)] = thread  # noqa: SLF001


class TestThreadService:
    """Tests for ThreadService behavior."""

    @pytest.mark.asyncio
    async def test_create_thread_persists_defaults(self, service, fake_dataservice):
        """Creating a thread initializes the persisted contract."""
        with (
            patch(
                "src.services.thread_service.validate_requested_model",
                return_value="resolved-tool-model",
            ) as validate_model,
            patch(
                "src.services.thread_service.route_model",
                return_value="resolved-tool-model",
            ),
        ):
            thread = await service.create_thread(
                user_id="user-1",
                workspace_id="ws-1",
                title="Draft thread",
                model="resolved-tool-model",
                skill="deep-research",
            )

        persisted = fake_dataservice.create_conversation_thread.await_args.args[0]
        assert validate_model.call_args.kwargs["allowed_categories"] == ("llm",)
        assert persisted.user_id == "user-1"
        assert persisted.workspace_id == "ws-1"
        assert persisted.title == "Draft thread"
        assert persisted.model == "resolved-tool-model"
        assert persisted.skill == "deep-research"
        assert thread.user_id == "user-1"
        assert thread.workspace_id == "ws-1"
        assert thread.title == "Draft thread"
        assert thread.model == "resolved-tool-model"
        assert thread.skill == "deep-research"

    @pytest.mark.asyncio
    async def test_create_thread_without_model_uses_resolved_default(self, service):
        """Missing model should resolve through llm_config default resolver."""
        with patch(
            "src.services.thread_service.route_model",
            return_value="resolved-model-id",
        ):
            thread = await service.create_thread(user_id="user-1")

        assert thread.model == "resolved-model-id"
        assert thread.skill is None

    @pytest.mark.asyncio
    async def test_create_thread_rejects_invalid_explicit_model(self, service, fake_dataservice):
        """Invalid explicit model ids should fail instead of being silently persisted."""
        with patch(
            "src.services.thread_service.validate_requested_model",
            side_effect=InvalidRequestedModelError("Unknown model id: bad-model"),
        ):
            with pytest.raises(InvalidRequestedModelError, match="Unknown model id: bad-model"):
                await service.create_thread(
                    user_id="user-1",
                    model="bad-model",
                )

        fake_dataservice.create_conversation_thread.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_create_thread_reuses_owned_thread(self, service, mock_db_session):
        """Existing owned threads are reused and can absorb workspace context."""
        thread = _make_thread(workspace_id=None)
        _store_thread(service, thread)

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            thread_id="thread-1",
            workspace_id="ws-2",
        )

        assert resolved.id == thread.id
        assert resolved.workspace_id == "ws-2"
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_get_or_create_thread_updates_model_when_explicitly_selected(
        self,
        service,
        mock_db_session,
    ):
        """Existing thread model is updated when user explicitly selects another model."""
        thread = _make_thread(workspace_id="ws-1")
        _store_thread(service, thread)

        with (
            patch(
                "src.services.thread_service.validate_requested_model",
                return_value="some-user-selected-model",
            ),
            patch(
                "src.services.thread_service.route_model",
                return_value="resolved-model-id",
            ),
        ):
            resolved = await service.get_or_create_thread(
                user_id="user-1",
                thread_id="thread-1",
                workspace_id="ws-1",
                model="some-user-selected-model",
            )

        assert resolved.id == thread.id
        assert resolved.model == "resolved-model-id"
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_get_or_create_thread_updates_skill_when_explicitly_selected(
        self,
        service,
        mock_db_session,
    ):
        """Existing thread skill is updated when user explicitly selects another skill."""
        thread = _make_thread(workspace_id="ws-1", skill="deep-research")
        _store_thread(service, thread)

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            thread_id="thread-1",
            workspace_id="ws-1",
            skill="literature-review",
            skill_explicit=True,
        )

        assert resolved.id == thread.id
        assert resolved.skill == "literature-review"
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_get_or_create_thread_reuses_latest_workspace_thread_without_thread_id(
        self,
        service,
        mock_db_session,
    ):
        """Workspace chat should reuse the latest thread when no explicit thread id is given."""
        thread = _make_thread(workspace_id="ws-1", skill="deep-research")
        _store_thread(service, thread)

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            workspace_id="ws-1",
        )

        assert resolved.id == thread.id
        service._dataservice.create_conversation_thread.assert_not_awaited()  # noqa: SLF001
        service._dataservice.update_conversation_thread.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_get_or_create_thread_rejects_other_users_thread(
        self,
        service,
        mock_db_session,
    ):
        """Cross-user thread access returns a not-found style error."""
        thread = _make_thread(user_id="user-2")
        _store_thread(service, thread)

        with pytest.raises(ThreadAccessError):
            await service.get_or_create_thread(
                user_id="user-1",
                thread_id="thread-1",
            )

    @pytest.mark.asyncio
    async def test_get_or_create_thread_rejects_missing_explicit_thread_id(
        self,
        service,
        mock_db_session,
    ):
        """Explicit thread ids must exist; no silent fallback is allowed."""
        with pytest.raises(ThreadAccessError):
            await service.get_or_create_thread(
                user_id="user-1",
                thread_id="thread-missing",
                workspace_id="ws-1",
            )

    @pytest.mark.asyncio
    async def test_add_message_writes_conversation_rows_not_json_history(self, service, mock_db_session):
        """Message append updates thread summary and delegates canonical storage to DataService."""
        thread = _make_thread()
        _store_thread(service, thread)

        message = await service.add_message(
            thread,
            role="user",
            content="Hello",
        )

        assert message["role"] == "user"
        assert message["content"] == "Hello"
        assert message["id"] == "msg-0"
        assert message["sequence_index"] == 0
        assert thread.message_count == 1
        assert thread.last_message_role == "user"
        assert thread.last_message_preview == "Hello"
        service._dataservice.append_conversation_message.assert_awaited_once()  # noqa: SLF001
        stored_message = service._dataservice.append_conversation_message.await_args.args[1]  # noqa: SLF001
        assert stored_message.content == "Hello"
        assert stored_message.sequence_index == 0

    @pytest.mark.asyncio
    async def test_update_attachment_extraction_state_updates_matching_attachment(
        self,
        service,
        mock_db_session,
    ):
        """Extraction task state should be written back into the matching attachment."""
        thread = _make_thread()
        source_messages = [
            {
                "role": "user",
                "content": "please read this paper",
                "metadata": {
                    "attachments": [
                        {
                            "name": "paper.pdf",
                            "metadata": {
                                "extraction": {
                                    "task_id": "task-paper-1",
                                    "status": "scheduled",
                                    "message": "queued",
                                }
                            },
                        }
                    ]
                },
            }
        ]
        _store_thread(service, thread)

        updated = await service.update_attachment_extraction_state(
            thread,
            task_id="task-paper-1",
            status="success",
            message="Paper extraction completed",
            progress=100,
            current_step="complete",
            source_messages=source_messages,
        )

        assert updated is True
        stored_messages = service._dataservice.rebuild_conversation_messages.await_args.args[1].messages  # noqa: SLF001
        extraction = stored_messages[0]["metadata"]["attachments"][0]["metadata"]["extraction"]
        assert extraction["status"] == "success"
        assert extraction["message"] == "Paper extraction completed"
        assert extraction["progress"] == 100
        assert extraction["current_step"] == "complete"
        assert thread.updated_at is not None
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_update_attachment_extraction_state_reads_projection_by_default(
        self,
        service,
    ):
        """Attachment state updates should use DataService projection messages by default."""
        thread = _make_thread()
        _store_thread(service, thread)
        service._dataservice.messages["thread-1"] = [  # noqa: SLF001
            {
                "role": "user",
                "content": "canonical message",
                "metadata": {
                    "attachments": [
                        {
                            "name": "paper.pdf",
                            "metadata": {
                                "extraction": {
                                    "task_id": "task-paper-1",
                                    "status": "scheduled",
                                }
                            },
                        }
                    ]
                },
            }
        ]

        updated = await service.update_attachment_extraction_state(
            thread,
            task_id="task-paper-1",
            status="success",
        )

        assert updated is True
        stored_messages = service._dataservice.rebuild_conversation_messages.await_args.args[1].messages  # noqa: SLF001
        assert stored_messages[0]["content"] == "canonical message"
        assert (
            stored_messages[0]["metadata"]["attachments"][0]["metadata"]["extraction"]["status"]
            == "success"
        )
        service._dataservice.list_conversation_messages.assert_awaited_once_with("thread-1")  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_update_attachment_preprocess_state_updates_matching_attachment(
        self,
        service,
        mock_db_session,
    ):
        """Preprocess task state should be written back into matching attachments."""
        thread = _make_thread()
        source_messages = [
            {
                "role": "user",
                "content": "please read this large pdf",
                "metadata": {
                    "attachments": [
                        {
                            "name": "paper.pdf",
                            "metadata": {
                                "preprocess": {
                                    "task_id": "task-preprocess-1",
                                    "status": "pending",
                                    "message": "queued",
                                }
                            },
                        }
                    ]
                },
            }
        ]
        _store_thread(service, thread)

        updated = await service.update_attachment_preprocess_state(
            thread,
            task_id="task-preprocess-1",
            status="success",
            preprocess={
                "status": "succeeded",
                "provider": "layout_parsing",
                "file_type": "pdf",
                "markdown_paths": ["/references/_preprocessed/paper/doc_0.md"],
            },
            message="Document preprocessing completed",
            progress=100,
            current_step="complete",
            source_messages=source_messages,
        )

        assert updated is True
        stored_messages = service._dataservice.rebuild_conversation_messages.await_args.args[1].messages  # noqa: SLF001
        attachment_metadata = stored_messages[0]["metadata"]["attachments"][0]["metadata"]
        preprocess = attachment_metadata["preprocess"]
        assert preprocess["task_id"] == "task-preprocess-1"
        assert preprocess["status"] == "succeeded"
        assert preprocess["message"] == "Document preprocessing completed"
        assert preprocess["progress"] == 100
        assert preprocess["current_step"] == "complete"
        assert attachment_metadata["preprocessed_markdown_paths"] == ["/references/_preprocessed/paper/doc_0.md"]
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_update_attachment_extraction_state_returns_false_when_missing_task(
        self,
        service,
        mock_db_session,
    ):
        """Non-matching attachments should not trigger writes."""
        thread = _make_thread()
        source_messages = [
            {
                "role": "user",
                "content": "hello",
                "metadata": {
                    "attachments": [
                        {
                            "name": "paper.pdf",
                            "metadata": {
                                "extraction": {
                                    "task_id": "another-task",
                                    "status": "scheduled",
                                }
                            },
                        }
                    ]
                },
            }
        ]

        updated = await service.update_attachment_extraction_state(
            thread,
            task_id="task-paper-1",
            status="failed",
            error="boom",
            source_messages=source_messages,
        )

        assert updated is False
        service._dataservice.update_conversation_thread.assert_not_awaited()  # noqa: SLF001
        service._dataservice.rebuild_conversation_messages.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_compact_messages_persists_summary_and_recent_tail(
        self,
        service,
        mock_db_session,
    ):
        thread = _make_thread()
        source_messages = [
            {"role": "user", "content": "old question", "timestamp": "2026-04-14T00:00:00+00:00"},
            {"role": "assistant", "content": "old answer", "timestamp": "2026-04-14T00:01:00+00:00"},
            {"role": "user", "content": "recent question", "timestamp": "2026-04-14T00:02:00+00:00"},
            {"role": "assistant", "content": "recent answer", "timestamp": "2026-04-14T00:03:00+00:00"},
        ]
        thread.message_count = 4
        _store_thread(service, thread)

        compacted = await service.compact_messages(
            thread,
            summary="old exchange summary",
            keep_messages=2,
            timestamp=datetime(2026, 4, 14, tzinfo=UTC),
            source_messages=source_messages,
        )

        assert compacted is True
        stored_messages = service._dataservice.rebuild_conversation_messages.await_args.args[1].messages  # noqa: SLF001
        assert len(stored_messages) == 3
        assert stored_messages[0]["role"] == "system"
        assert stored_messages[0]["metadata"]["type"] == "thread_compaction"
        assert stored_messages[0]["metadata"]["compacted_message_count"] == 2
        assert "old exchange summary" in stored_messages[0]["content"]
        assert [message["content"] for message in stored_messages[1:]] == [
            "recent question",
            "recent answer",
        ]
        assert thread.message_count == 3
        assert thread.last_message_role == "assistant"
        assert thread.last_message_preview == "recent answer"
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_rollback_last_user_message_removes_tail_user_turn(
        self,
        service,
        mock_db_session,
    ):
        """Rollback should remove the most recent user message and refresh summary fields."""
        thread = _make_thread()
        source_messages = [
            {
                "role": "assistant",
                "content": "previous answer",
                "timestamp": "2026-04-14T00:00:00+00:00",
            },
            {
                "role": "user",
                "content": "new question",
                "timestamp": "2026-04-14T00:01:00+00:00",
            },
        ]
        thread.message_count = 2
        thread.last_message_role = "user"
        thread.last_message_preview = "new question"
        _store_thread(service, thread)

        rolled_back = await service.rollback_last_user_message(
            thread,
            expected_content="new question",
            source_messages=source_messages,
        )

        assert rolled_back is True
        stored_messages = service._dataservice.rebuild_conversation_messages.await_args.args[1].messages  # noqa: SLF001
        assert len(stored_messages) == 1
        assert stored_messages[0]["role"] == "assistant"
        assert thread.message_count == 1
        assert thread.last_message_role == "assistant"
        assert thread.last_message_preview == "previous answer"
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_rollback_last_user_message_requires_matching_tail(
        self,
        service,
        mock_db_session,
    ):
        """Rollback should be a no-op when trailing message does not match request content."""
        thread = _make_thread()
        source_messages = [
            {
                "role": "assistant",
                "content": "already done",
                "timestamp": "2026-04-14T00:00:00+00:00",
            }
        ]
        thread.message_count = 1
        thread.last_message_role = "assistant"
        thread.last_message_preview = "already done"

        rolled_back = await service.rollback_last_user_message(
            thread,
            expected_content="new question",
            source_messages=source_messages,
        )

        assert rolled_back is False
        assert thread.message_count == 1
        service._dataservice.update_conversation_thread.assert_not_awaited()  # noqa: SLF001
        service._dataservice.rebuild_conversation_messages.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_list_thread_messages_reads_conversation_projection(self, service):
        """Thread API readers should use DataService conversation rows."""
        thread = _make_thread()
        _store_thread(service, thread)
        service._dataservice.messages["thread-1"] = [  # noqa: SLF001
            {"role": "assistant", "content": "canonical"}
        ]

        messages = await service.list_thread_messages(thread)

        assert messages == [{"role": "assistant", "content": "canonical", "timestamp": None}]
        service._dataservice.list_conversation_messages.assert_awaited_once_with("thread-1")  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_set_title_if_empty_only_updates_opening_exchange(
        self,
        service,
        mock_db_session,
    ):
        """Title derivation only applies to the first user-assistant exchange."""
        thread = _make_thread()
        thread.message_count = 2
        _store_thread(service, thread)

        await service.set_title_if_empty(
            thread,
            "A much longer opening message that should still become a title",
        )

        assert thread.title is not None
        assert thread.title.startswith("A much longer opening message")
        service._dataservice.update_conversation_thread.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_delete_thread_removes_local_thread_directory(
        self,
        service,
        mock_db_session,
    ):
        """Deleting a thread also cleans its persisted local thread directory."""
        thread = _make_thread()

        with (
            patch.object(
                service,
                "get_thread",
                AsyncMock(return_value=thread),
            ),
            patch(
                "src.services.thread_service.delete_thread_directory",
            ) as delete_thread_directory,
        ):
            _store_thread(service, thread)
            deleted = await service.delete_thread("thread-1", "user-1")

        assert deleted is True
        service._dataservice.delete_conversation_thread.assert_awaited_once_with(  # noqa: SLF001
            thread_id="thread-1",
            user_id="user-1",
        )
        delete_thread_directory.assert_called_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_delete_thread_survives_cleanup_failure(
        self,
        service,
        mock_db_session,
    ):
        """Filesystem cleanup is best-effort and must not mask a successful delete."""
        thread = _make_thread()

        with (
            patch.object(
                service,
                "get_thread",
                AsyncMock(return_value=thread),
            ),
            patch(
                "src.services.thread_service.delete_thread_directory",
                side_effect=RuntimeError("boom"),
            ),
        ):
            _store_thread(service, thread)
            deleted = await service.delete_thread("thread-1", "user-1")

        assert deleted is True
        service._dataservice.delete_conversation_thread.assert_awaited_once_with(  # noqa: SLF001
            thread_id="thread-1",
            user_id="user-1",
        )
