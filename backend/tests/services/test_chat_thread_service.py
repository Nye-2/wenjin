"""Tests for ChatThreadService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database import ChatThread
from src.models.router import InvalidRequestedModelError
from src.services.chat_thread_service import ChatThreadAccessError, ChatThreadService


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
def service(mock_db_session):
    """Create ChatThreadService instance."""
    return ChatThreadService(mock_db_session)


def _make_thread(
    *,
    user_id: str = "user-1",
    workspace_id: str | None = None,
    title: str | None = None,
    skill: str | None = None,
) -> ChatThread:
    thread = ChatThread(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        model="gpt-4o",
        skill=skill,
        messages=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    thread.id = "thread-1"
    return thread


class TestChatThreadService:
    """Tests for ChatThreadService behavior."""

    @pytest.mark.asyncio
    async def test_create_thread_persists_defaults(self, service, mock_db_session):
        """Creating a thread initializes the persisted contract."""
        with patch(
            "src.services.chat_thread_service.validate_requested_model",
            return_value="gpt-4o-mini",
        ), patch(
            "src.services.chat_thread_service.route_model",
            return_value="gpt-4o-mini",
        ):
            thread = await service.create_thread(
                user_id="user-1",
                workspace_id="ws-1",
                title="Draft thread",
                model="gpt-4o-mini",
                skill="deep-research",
            )

        mock_db_session.add.assert_called_once_with(thread)
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)
        assert thread.user_id == "user-1"
        assert thread.workspace_id == "ws-1"
        assert thread.title == "Draft thread"
        assert thread.model == "gpt-4o-mini"
        assert thread.skill == "deep-research"
        assert thread.messages == []

    @pytest.mark.asyncio
    async def test_create_thread_without_model_uses_resolved_default(self, service):
        """Missing model should resolve through llm_config default resolver."""
        with patch(
            "src.services.chat_thread_service.route_model",
            return_value="resolved-model-id",
        ):
            thread = await service.create_thread(user_id="user-1")

        assert thread.model == "resolved-model-id"
        assert thread.skill is None

    @pytest.mark.asyncio
    async def test_create_thread_rejects_invalid_explicit_model(self, service, mock_db_session):
        """Invalid explicit model ids should fail instead of being silently persisted."""
        with patch(
            "src.services.chat_thread_service.validate_requested_model",
            side_effect=InvalidRequestedModelError("Unknown model id: bad-model"),
        ):
            with pytest.raises(InvalidRequestedModelError, match="Unknown model id: bad-model"):
                await service.create_thread(
                    user_id="user-1",
                    model="bad-model",
                )

        mock_db_session.add.assert_not_called()
        mock_db_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_create_thread_reuses_owned_thread(self, service, mock_db_session):
        """Existing owned threads are reused and can absorb workspace context."""
        thread = _make_thread(workspace_id=None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = thread
        mock_db_session.execute.return_value = result

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            thread_id="thread-1",
            workspace_id="ws-2",
        )

        assert resolved is thread
        assert resolved.workspace_id == "ws-2"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_get_or_create_thread_updates_model_when_explicitly_selected(
        self,
        service,
        mock_db_session,
    ):
        """Existing thread model is updated when user explicitly selects another model."""
        thread = _make_thread(workspace_id="ws-1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = thread
        mock_db_session.execute.return_value = result

        with patch(
            "src.services.chat_thread_service.validate_requested_model",
            return_value="some-user-selected-model",
        ), patch(
            "src.services.chat_thread_service.route_model",
            return_value="resolved-model-id",
        ):
            resolved = await service.get_or_create_thread(
                user_id="user-1",
                thread_id="thread-1",
                workspace_id="ws-1",
                model="some-user-selected-model",
            )

        assert resolved is thread
        assert resolved.model == "resolved-model-id"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_get_or_create_thread_updates_skill_when_explicitly_selected(
        self,
        service,
        mock_db_session,
    ):
        """Existing thread skill is updated when user explicitly selects another skill."""
        thread = _make_thread(workspace_id="ws-1", skill="deep-research")
        result = MagicMock()
        result.scalar_one_or_none.return_value = thread
        mock_db_session.execute.return_value = result

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            thread_id="thread-1",
            workspace_id="ws-1",
            skill="literature-review",
            skill_explicit=True,
        )

        assert resolved is thread
        assert resolved.skill == "literature-review"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_get_or_create_thread_reuses_latest_workspace_thread_without_thread_id(
        self,
        service,
        mock_db_session,
    ):
        """Workspace chat should reuse the latest thread when no explicit thread id is given."""
        thread = _make_thread(workspace_id="ws-1", skill="deep-research")
        result = MagicMock()
        result.scalar_one_or_none.return_value = thread
        mock_db_session.execute.return_value = result

        resolved = await service.get_or_create_thread(
            user_id="user-1",
            workspace_id="ws-1",
        )

        assert resolved is thread
        mock_db_session.add.assert_not_called()
        mock_db_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_create_thread_rejects_other_users_thread(
        self,
        service,
        mock_db_session,
    ):
        """Cross-user thread access returns a not-found style error."""
        thread = _make_thread(user_id="user-2")
        result = MagicMock()
        result.scalar_one_or_none.return_value = thread
        mock_db_session.execute.return_value = result

        with pytest.raises(ChatThreadAccessError):
            await service.get_or_create_thread(
                user_id="user-1",
                thread_id="thread-1",
            )

    @pytest.mark.asyncio
    async def test_add_message_appends_json_history(self, service, mock_db_session):
        """Message append reassigns JSON history so ORM persistence can detect it."""
        thread = _make_thread()

        message = await service.add_message(
            thread,
            role="user",
            content="Hello",
        )

        assert message["role"] == "user"
        assert message["content"] == "Hello"
        assert len(thread.messages) == 1
        assert thread.messages[0]["content"] == "Hello"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_update_attachment_extraction_state_updates_matching_attachment(
        self,
        service,
        mock_db_session,
    ):
        """Extraction task state should be written back into the matching attachment."""
        thread = _make_thread()
        thread.messages = [
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

        updated = await service.update_attachment_extraction_state(
            thread,
            task_id="task-paper-1",
            status="success",
            message="Paper extraction completed",
            progress=100,
            current_step="complete",
        )

        assert updated is True
        extraction = thread.messages[0]["metadata"]["attachments"][0]["metadata"]["extraction"]
        assert extraction["status"] == "success"
        assert extraction["message"] == "Paper extraction completed"
        assert extraction["progress"] == 100
        assert extraction["current_step"] == "complete"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_update_attachment_extraction_state_returns_false_when_missing_task(
        self,
        service,
        mock_db_session,
    ):
        """Non-matching attachments should not trigger writes."""
        thread = _make_thread()
        thread.messages = [
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
        )

        assert updated is False
        mock_db_session.commit.assert_not_awaited()
        mock_db_session.refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_title_if_empty_only_updates_opening_exchange(
        self,
        service,
        mock_db_session,
    ):
        """Title derivation only applies to the first user-assistant exchange."""
        thread = _make_thread()
        thread.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]

        await service.set_title_if_empty(
            thread,
            "A much longer opening message that should still become a title",
        )

        assert thread.title is not None
        assert thread.title.startswith("A much longer opening message")
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)

    @pytest.mark.asyncio
    async def test_delete_thread_removes_local_thread_directory(
        self,
        service,
        mock_db_session,
    ):
        """Deleting a thread also cleans its persisted local thread directory."""
        thread = _make_thread()

        with patch.object(
            service,
            "get_thread",
            AsyncMock(return_value=thread),
        ), patch(
            "src.services.chat_thread_service.delete_thread_directory",
        ) as delete_thread_directory:
            deleted = await service.delete_thread("thread-1", "user-1")

        assert deleted is True
        mock_db_session.delete.assert_awaited_once_with(thread)
        mock_db_session.commit.assert_awaited_once()
        delete_thread_directory.assert_called_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_delete_thread_survives_cleanup_failure(
        self,
        service,
        mock_db_session,
    ):
        """Filesystem cleanup is best-effort and must not mask a successful delete."""
        thread = _make_thread()

        with patch.object(
            service,
            "get_thread",
            AsyncMock(return_value=thread),
        ), patch(
            "src.services.chat_thread_service.delete_thread_directory",
            side_effect=RuntimeError("boom"),
        ):
            deleted = await service.delete_thread("thread-1", "user-1")

        assert deleted is True
        mock_db_session.delete.assert_awaited_once_with(thread)
        mock_db_session.commit.assert_awaited_once()
