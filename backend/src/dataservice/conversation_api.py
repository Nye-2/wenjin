"""Public in-process conversation API for DataService."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.conversation.contracts import (
    ConversationMessageRecord,
    ConversationThreadCreateCommand,
    ConversationThreadProjection,
    ConversationThreadUpdateCommand,
)
from src.dataservice.domains.conversation.service import DataServiceConversationService

if TYPE_CHECKING:
    from src.database import Thread


class ConversationDataService:
    """Conversation API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceConversationService(session, autocommit=autocommit)

    async def create_thread(
        self,
        command: ConversationThreadCreateCommand,
    ) -> ConversationThreadProjection:
        return await self._domain.create_thread(command)

    async def get_thread(self, thread_id: str) -> ConversationThreadProjection | None:
        return await self._domain.get_thread(thread_id)

    async def get_owned_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> ConversationThreadProjection | None:
        return await self._domain.get_owned_thread(thread_id=thread_id, user_id=user_id)

    async def get_latest_workspace_thread(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> ConversationThreadProjection | None:
        return await self._domain.get_latest_workspace_thread(
            user_id=user_id,
            workspace_id=workspace_id,
        )

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[ConversationThreadProjection]:
        return await self._domain.list_threads(
            user_id=user_id,
            workspace_id=workspace_id,
            limit=limit,
        )

    async def update_thread(
        self,
        thread_id: str,
        command: ConversationThreadUpdateCommand,
    ) -> ConversationThreadProjection | None:
        return await self._domain.update_thread(thread_id, command)

    async def delete_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> bool:
        return await self._domain.delete_thread(thread_id=thread_id, user_id=user_id)

    async def lock_thread(self, thread_id: str) -> None:
        await self._domain.lock_thread(thread_id)

    async def append_thread_message(
        self,
        thread: Thread,
        message: Mapping[str, Any],
        *,
        sequence_index: int,
    ) -> None:
        await self._domain.append_thread_message(
            thread,
            message,
            sequence_index=sequence_index,
        )

    async def replace_thread_messages(
        self,
        thread: Thread,
        messages: list[dict[str, Any]],
    ) -> None:
        await self._domain.replace_thread_messages(thread, messages)

    async def list_message_records(self, thread_id: str) -> list[ConversationMessageRecord]:
        return await self._domain.list_message_records(thread_id)

    async def list_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return await self._domain.list_thread_messages(thread_id)

    async def list_workspace_thread_summaries(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[ConversationThreadProjection]:
        return await self._domain.list_workspace_thread_summaries(
            workspace_id=workspace_id,
            limit=limit,
        )
