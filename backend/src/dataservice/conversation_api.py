"""Public in-process conversation API for DataService."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Thread
from src.dataservice.domains.conversation.contracts import (
    ConversationMessageRecord,
    ConversationThreadProjection,
)
from src.dataservice.domains.conversation.service import DataServiceConversationService


class ConversationDataService:
    """Conversation API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceConversationService(session, autocommit=autocommit)

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
