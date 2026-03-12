"""Tests for ChatThreadService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database import ChatThread
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
) -> ChatThread:
    thread = ChatThread(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        model="gpt-4o",
        messages=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    thread.id = "thread-1"
    return thread


class TestChatThreadService:
    """Tests for ChatThreadService behavior."""

    @pytest.mark.asyncio
    async def test_create_thread_persists_defaults(self, service, mock_db_session):
        """Creating a thread initializes the persisted contract."""
        thread = await service.create_thread(
            user_id="user-1",
            workspace_id="ws-1",
            title="Draft thread",
            model="gpt-4o-mini",
        )

        mock_db_session.add.assert_called_once_with(thread)
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(thread)
        assert thread.user_id == "user-1"
        assert thread.workspace_id == "ws-1"
        assert thread.title == "Draft thread"
        assert thread.model == "gpt-4o-mini"
        assert thread.messages == []

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
