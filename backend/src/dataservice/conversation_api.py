"""Public in-process conversation API for DataService."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Thread
from src.dataservice.domains.conversation.contracts import ConversationMessageRecord
from src.dataservice.domains.conversation.service import DataServiceConversationService


class ConversationDataService:
    """Conversation API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceConversationService(session, autocommit=autocommit)

    async def append_bridge_message(
        self,
        thread: Thread,
        message: Mapping[str, Any],
        *,
        sequence_index: int,
    ) -> None:
        await self._domain.append_bridge_message(
            thread,
            message,
            sequence_index=sequence_index,
        )

    async def rebuild_thread_bridge(self, thread: Thread) -> None:
        await self._domain.rebuild_thread_bridge(thread)

    async def list_message_records(self, thread_id: str) -> list[ConversationMessageRecord]:
        return await self._domain.list_message_records(thread_id)

    async def list_bridge_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return await self._domain.list_bridge_messages(thread_id)
