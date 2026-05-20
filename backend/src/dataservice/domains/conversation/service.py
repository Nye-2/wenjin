"""Conversation aggregate command service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.thread import Thread
from src.dataservice.domains.conversation.block_protocol import (
    blocks_from_message,
    canonical_block_kind,
    normalize_block_payload,
)
from src.dataservice.domains.conversation.contracts import (
    ConversationBlockRecord,
    ConversationMessageCreateCommand,
    ConversationMessageRecord,
    ConversationMessagesRebuildCommand,
)
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage
from src.dataservice.domains.conversation.repository import ConversationRepository


class DataServiceConversationService:
    """DataService-owned conversation message and block operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ConversationRepository(session)

    async def append_message(self, command: ConversationMessageCreateCommand) -> ThreadMessage:
        message = self.repository.create_message(
            thread_id=command.thread_id,
            workspace_id=command.workspace_id,
            user_id=command.user_id,
            role=command.role,
            content=command.content,
            sequence_index=command.sequence_index,
            timestamp=command.timestamp,
            metadata_json=dict(command.metadata or {}),
            source_json=dict(command.source_json or {}),
        )
        raw_blocks = command.blocks or blocks_from_message(
            {
                "content": command.content,
                "blocks": command.blocks,
            }
        )
        for index, block in enumerate(raw_blocks):
            payload = normalize_block_payload(block) if isinstance(block, Mapping) else {}
            self.repository.create_block(
                message_id=message.id,
                thread_id=command.thread_id,
                block_type=canonical_block_kind(payload),
                sequence_index=index,
                payload_json=payload,
            )
        await self._finish()
        return message

    async def rebuild_messages(self, command: ConversationMessagesRebuildCommand) -> list[ThreadMessage]:
        await self.repository.delete_thread_messages(command.thread_id)
        created: list[ThreadMessage] = []
        for index, raw_message in enumerate(command.messages):
            if not isinstance(raw_message, Mapping):
                continue
            created.append(
                self._materialize_bridge_message(
                    thread_id=command.thread_id,
                    workspace_id=command.workspace_id,
                    user_id=command.user_id,
                    message=raw_message,
                    sequence_index=index,
                )
            )
        await self._finish()
        return created

    async def append_bridge_message(
        self,
        thread: Thread,
        message: Mapping[str, Any],
        *,
        sequence_index: int,
    ) -> ThreadMessage:
        command = self._command_from_bridge_message(
            thread,
            message,
            sequence_index=sequence_index,
        )
        return await self.append_message(command)

    async def rebuild_thread_bridge(self, thread: Thread) -> list[ThreadMessage]:
        return await self.rebuild_messages(
            ConversationMessagesRebuildCommand(
                thread_id=str(thread.id),
                user_id=str(thread.user_id),
                workspace_id=str(thread.workspace_id) if thread.workspace_id else None,
                messages=[message for message in list(thread.messages or []) if isinstance(message, dict)],
            )
        )

    async def list_message_records(self, thread_id: str) -> list[ConversationMessageRecord]:
        messages = await self.repository.list_messages(thread_id)
        blocks = await self.repository.list_blocks_for_messages([message.id for message in messages])
        blocks_by_message: dict[str, list[MessageBlock]] = {}
        for block in blocks:
            blocks_by_message.setdefault(block.message_id, []).append(block)
        return [
            self.to_message_record(message, blocks=blocks_by_message.get(message.id, []))
            for message in messages
        ]

    def _materialize_bridge_message(
        self,
        *,
        thread_id: str,
        workspace_id: str | None,
        user_id: str,
        message: Mapping[str, Any],
        sequence_index: int,
    ) -> ThreadMessage:
        command = ConversationMessageCreateCommand(
            thread_id=thread_id,
            user_id=user_id,
            workspace_id=workspace_id,
            role=str(message.get("role") or "unknown"),
            content=str(message.get("content") or ""),
            sequence_index=sequence_index,
            timestamp=self._coerce_timestamp(message.get("timestamp")),
            blocks=blocks_from_message(message),
            metadata=dict(message.get("metadata") or {}) if isinstance(message.get("metadata"), Mapping) else {},
            source_json=dict(message),
        )
        created = self.repository.create_message(
            thread_id=command.thread_id,
            workspace_id=command.workspace_id,
            user_id=command.user_id,
            role=command.role,
            content=command.content,
            sequence_index=command.sequence_index,
            timestamp=command.timestamp,
            metadata_json=command.metadata,
            source_json=command.source_json,
        )
        for block_index, payload in enumerate(command.blocks):
            self.repository.create_block(
                message_id=created.id,
                thread_id=command.thread_id,
                block_type=canonical_block_kind(payload),
                sequence_index=block_index,
                payload_json=payload,
            )
        return created

    def _command_from_bridge_message(
        self,
        thread: Thread,
        message: Mapping[str, Any],
        *,
        sequence_index: int,
    ) -> ConversationMessageCreateCommand:
        return ConversationMessageCreateCommand(
            thread_id=str(thread.id),
            user_id=str(thread.user_id),
            workspace_id=str(thread.workspace_id) if thread.workspace_id else None,
            role=str(message.get("role") or "unknown"),
            content=str(message.get("content") or ""),
            sequence_index=sequence_index,
            timestamp=self._coerce_timestamp(message.get("timestamp")),
            blocks=blocks_from_message(message),
            metadata=dict(message.get("metadata") or {}) if isinstance(message.get("metadata"), Mapping) else {},
            source_json=dict(message),
        )

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    @staticmethod
    def _coerce_timestamp(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def to_message_record(
        message: ThreadMessage,
        *,
        blocks: list[MessageBlock],
    ) -> ConversationMessageRecord:
        return ConversationMessageRecord(
            id=str(message.id),
            thread_id=str(message.thread_id),
            user_id=str(message.user_id),
            workspace_id=message.workspace_id,
            role=message.role,
            content=message.content,
            sequence_index=message.sequence_index,
            timestamp=message.timestamp,
            metadata_json=dict(message.metadata_json or {}),
            blocks=[
                ConversationBlockRecord(
                    id=str(block.id),
                    message_id=str(block.message_id),
                    thread_id=str(block.thread_id),
                    block_type=block.block_type,
                    sequence_index=block.sequence_index,
                    payload_json=dict(block.payload_json or {}),
                )
                for block in blocks
            ],
            created_at=message.created_at,
            updated_at=message.updated_at,
        )
