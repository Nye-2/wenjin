"""Gateway-side adapter for the DataService chat-turn billing transaction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from src.contracts.model_usage import ModelUsage
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationThreadPayload,
)
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnAuthorizationResultPayload,
    ThreadTurnAuthorizePayload,
    ThreadTurnCompletePayload,
    ThreadTurnCompletionResultPayload,
    ThreadTurnReleaseByKeyPayload,
    ThreadTurnReleasePayload,
    ThreadTurnRollbackPayload,
)
from src.dataservice_client.provider import dataservice_client


class ThreadTurnBillingGateway:
    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def authorize(
        self,
        *,
        thread: ConversationThreadPayload,
        content: str,
        metadata: dict[str, Any] | None,
        idempotency_key: str,
    ) -> ThreadTurnAuthorizationResultPayload:
        now = datetime.now(UTC)
        command = ThreadTurnAuthorizePayload(
            idempotency_key=idempotency_key,
            model_id=str(thread.model or ""),
            user_message=ConversationMessageCreatePayload(
                thread_id=str(thread.id),
                user_id=str(thread.user_id),
                workspace_id=thread.workspace_id,
                role="user",
                content=content,
                sequence_index=max(int(thread.message_count or 0), 0),
                timestamp=now,
                metadata=dict(metadata or {}),
            ),
        )
        async with self._client() as client:
            result = await client.thread_turn_billings.authorize(command)
        if result.user_message is not None:
            _sync_thread_projection(thread, result.user_message)
        if result.assistant_message is not None:
            _sync_thread_projection(thread, result.assistant_message)
        return result

    async def complete(
        self,
        *,
        thread: ConversationThreadPayload,
        billing_id: str,
        content: str,
        blocks: list[dict[str, Any]],
        metadata: dict[str, Any],
        usage: ModelUsage,
    ) -> ThreadTurnCompletionResultPayload:
        command = ThreadTurnCompletePayload(
            user_id=str(thread.user_id),
            assistant_message=ConversationMessageCreatePayload(
                thread_id=str(thread.id),
                user_id=str(thread.user_id),
                workspace_id=thread.workspace_id,
                role="assistant",
                content=content,
                sequence_index=max(int(thread.message_count or 0), 0),
                timestamp=datetime.now(UTC),
                blocks=[dict(item) for item in blocks if isinstance(item, Mapping)],
                metadata=dict(metadata),
            ),
            token_usage=usage,
        )
        async with self._client() as client:
            result = await client.thread_turn_billings.complete(
                billing_id,
                command,
            )
        _sync_thread_projection(thread, result.assistant_message)
        return result

    async def release(
        self,
        *,
        billing_id: str,
        user_id: str,
        reason: str,
    ) -> None:
        async with self._client() as client:
            await client.thread_turn_billings.release(
                billing_id,
                ThreadTurnReleasePayload(user_id=user_id, reason=reason[:1000]),
            )

    async def release_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
        user_id: str,
        reason: str,
    ) -> None:
        async with self._client() as client:
            await client.thread_turn_billings.release_by_idempotency_key(
                ThreadTurnReleaseByKeyPayload(
                    idempotency_key=idempotency_key,
                    user_id=user_id,
                    reason=reason[:1000],
                )
            )

    async def rollback(
        self,
        *,
        thread: ConversationThreadPayload,
        billing_id: str,
        user_id: str,
        reason: str,
    ) -> bool:
        async with self._client() as client:
            result = await client.thread_turn_billings.rollback(
                billing_id,
                ThreadTurnRollbackPayload(user_id=user_id, reason=reason[:1000]),
            )
            if result.message_rolled_back:
                refreshed = await client.get_conversation_thread(str(thread.id))
                if refreshed is not None:
                    _copy_thread_projection(thread, refreshed)
        return result.message_rolled_back


def message_payload_to_bridge(
    message: ConversationMessagePayload,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "sequence_index": message.sequence_index,
        "timestamp": message.timestamp.isoformat() if message.timestamp else None,
    }
    if message.metadata_json:
        result["metadata"] = dict(message.metadata_json)
    if message.blocks:
        result["blocks"] = [dict(item.payload_json) for item in message.blocks]
    return result


def _sync_thread_projection(
    thread: ConversationThreadPayload,
    message: ConversationMessagePayload,
) -> None:
    thread.message_count = message.sequence_index + 1
    thread.last_message_role = message.role
    normalized = " ".join(message.content.split())
    thread.last_message_preview = (
        normalized
        if len(normalized) <= 120
        else normalized[:117].rstrip() + "..."
    ) or None
    thread.updated_at = message.timestamp or datetime.now(UTC)


def _copy_thread_projection(
    target: ConversationThreadPayload,
    source: ConversationThreadPayload,
) -> None:
    target.message_count = source.message_count
    target.last_message_role = source.last_message_role
    target.last_message_preview = source.last_message_preview
    target.updated_at = source.updated_at


__all__ = ["ThreadTurnBillingGateway", "message_payload_to_bridge"]
