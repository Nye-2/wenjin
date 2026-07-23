"""Mission lifecycle chat cards persisted into the owning thread.

Each Mission event is appended as one assistant message carrying a
single ``mission_card`` block so the chat surface can render Mission
progress inline. Cards are idempotent on ``metadata.card_id`` and every
emission is best-effort: failures are logged and never roll back the
Mission transaction that produced the event.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.session import get_async_session_factory
from src.dataservice.domains.conversation.block_protocol import ConversationBlockKind
from src.dataservice.domains.conversation.contracts import (
    ConversationMessageCreateCommand,
)
from src.dataservice.domains.conversation.service import DataServiceConversationService
from src.workspace_events import publish_workspace_event

if TYPE_CHECKING:
    from src.database.models.mission import MissionRunRecord

logger = logging.getLogger(__name__)

TERMINAL_CARD_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class MissionChatCardContext:
    """Primitive Mission identity captured before the transaction commits."""

    mission_id: str
    thread_id: str
    user_id: str
    workspace_id: str | None
    title: str

    @classmethod
    def from_run(cls, run: MissionRunRecord) -> MissionChatCardContext:
        return cls(
            mission_id=str(run.mission_id),
            thread_id=str(run.thread_id),
            user_id=str(run.user_id),
            workspace_id=str(run.workspace_id) if run.workspace_id else None,
            title=str(run.title or ""),
        )


class MissionChatCardEmitter:
    """Append idempotent Mission card messages to the Mission thread."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory

    async def stage_passed(
        self,
        context: MissionChatCardContext,
        *,
        stage_id: str,
        stage_title: str,
        evidence_count: int,
    ) -> None:
        """Emit one card for a stage whose acceptance just passed."""
        await self._emit(
            context,
            card_id=f"{context.mission_id}:stage_passed:{stage_id}",
            card="stage_passed",
            payload={
                "stage_id": stage_id,
                "stage_title": stage_title,
                "evidence_count": int(evidence_count),
            },
        )

    async def review_request_created(
        self,
        context: MissionChatCardContext,
        *,
        review_items: Sequence[Mapping[str, Any]],
    ) -> None:
        """Emit one card summarizing a freshly created review batch."""
        items = [
            {
                "review_item_id": str(item.get("review_item_id") or ""),
                "title": str(item.get("title") or ""),
            }
            for item in review_items
            if str(item.get("review_item_id") or "").strip()
        ]
        if not items:
            return
        await self._emit(
            context,
            card_id=f"{context.mission_id}:review_request:{items[0]['review_item_id']}",
            card="review_request",
            payload={
                "review_item_ids": [item["review_item_id"] for item in items],
                "count": len(items),
                "items": items,
            },
        )

    async def material_request_created(
        self,
        context: MissionChatCardContext,
        *,
        request_id: str,
        title: str,
        summary: str,
    ) -> None:
        """Emit one card for a pause that waits on user-supplied input."""
        await self._emit(
            context,
            card_id=f"{context.mission_id}:material_request:{request_id}",
            card="material_request",
            payload={
                "request_id": request_id,
                "title": title,
                "summary": summary,
            },
        )

    async def terminal(
        self,
        context: MissionChatCardContext,
        *,
        status: str,
    ) -> None:
        """Emit one card when the Mission reaches a terminal status."""
        if status not in TERMINAL_CARD_STATUSES:
            return
        await self._emit(
            context,
            card_id=f"{context.mission_id}:terminal:{status}",
            card="terminal",
            payload={
                "status": status,
                "title": context.title,
            },
        )

    async def _emit(
        self,
        context: MissionChatCardContext,
        *,
        card_id: str,
        card: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            block = {
                "kind": ConversationBlockKind.MISSION_CARD.value,
                "card": card,
                "mission_id": context.mission_id,
                **payload,
            }
            metadata = {
                "card_id": card_id,
                "card": card,
                "mission_id": context.mission_id,
            }
            session_factory = self._session_factory or get_async_session_factory()
            async with session_factory() as session:
                service = DataServiceConversationService(session, autocommit=True)
                _, created = await service.append_card_message(
                    ConversationMessageCreateCommand(
                        thread_id=context.thread_id,
                        user_id=context.user_id,
                        workspace_id=context.workspace_id,
                        role="assistant",
                        content="",
                        sequence_index=0,
                        blocks=[block],
                        metadata=metadata,
                    ),
                    card_id=card_id,
                )
            if created:
                await publish_workspace_event(
                    context.workspace_id,
                    "thread.updated",
                    {
                        "thread": {
                            "id": context.thread_id,
                            "workspace_id": context.workspace_id,
                        }
                    },
                )
        except Exception:
            logger.warning(
                "Mission chat card emission failed: mission_id=%s card_id=%s",
                context.mission_id,
                card_id,
                exc_info=True,
            )


__all__ = [
    "MissionChatCardContext",
    "MissionChatCardEmitter",
    "TERMINAL_CARD_STATUSES",
]
