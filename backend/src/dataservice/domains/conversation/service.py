"""Conversation aggregate command service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
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
    ConversationThreadCreateCommand,
    ConversationThreadProjection,
    ConversationThreadUpdateCommand,
)
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage
from src.dataservice.domains.conversation.repository import ConversationRepository


class DataServiceConversationService:
    """DataService-owned conversation message and block operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ConversationRepository(session)

    async def create_thread(
        self,
        command: ConversationThreadCreateCommand,
    ) -> ConversationThreadProjection:
        now = datetime.now(UTC)
        thread = self.repository.create_thread(
            {
                "user_id": command.user_id,
                "workspace_id": command.workspace_id,
                "title": command.title,
                "model": command.model,
                "skill": command.skill,
                "message_count": 0,
                "last_message_preview": None,
                "last_message_role": None,
                "created_at": command.created_at or now,
                "updated_at": command.updated_at or command.created_at or now,
            }
        )
        await self._finish()
        return self.to_thread_projection(thread)

    async def lock_thread(self, thread_id: str) -> None:
        await self.repository.lock_thread(thread_id)
        await self._finish()

    async def get_thread(self, thread_id: str) -> ConversationThreadProjection | None:
        thread = await self.repository.get_thread(thread_id)
        return self.to_thread_projection(thread) if thread is not None else None

    async def get_owned_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> ConversationThreadProjection | None:
        thread = await self.repository.get_owned_thread(
            thread_id=thread_id,
            user_id=user_id,
        )
        return self.to_thread_projection(thread) if thread is not None else None

    async def get_latest_workspace_thread(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> ConversationThreadProjection | None:
        thread = await self.repository.get_latest_workspace_thread(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return self.to_thread_projection(thread) if thread is not None else None

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[ConversationThreadProjection]:
        return [
            self.to_thread_projection(thread)
            for thread in await self.repository.list_threads(
                user_id=user_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    async def update_thread(
        self,
        thread_id: str,
        command: ConversationThreadUpdateCommand,
    ) -> ConversationThreadProjection | None:
        thread = await self.repository.get_thread(thread_id)
        if thread is None:
            return None
        data = command.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(thread, key, value)
        await self._finish()
        return self.to_thread_projection(thread)

    async def delete_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> bool:
        thread = await self.repository.get_owned_thread(
            thread_id=thread_id,
            user_id=user_id,
        )
        if thread is None:
            return False
        await self.repository.delete_thread(thread)
        await self._finish()
        return True

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

    async def append_thread_message(
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

    async def replace_thread_messages(
        self,
        thread: Thread,
        messages: list[dict[str, Any]],
    ) -> list[ThreadMessage]:
        return await self.rebuild_messages(
            ConversationMessagesRebuildCommand(
                thread_id=str(thread.id),
                user_id=str(thread.user_id),
                workspace_id=str(thread.workspace_id) if thread.workspace_id else None,
                messages=[message for message in messages if isinstance(message, dict)],
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

    async def list_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Project canonical conversation rows into the public API message shape."""
        return [
            self.to_bridge_message(record)
            for record in await self.list_message_records(thread_id)
        ]

    async def list_workspace_thread_summaries(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[ConversationThreadProjection]:
        return [
            self.to_thread_projection(thread)
            for thread in await self.repository.list_workspace_threads(
                workspace_id=workspace_id,
                limit=limit,
            )
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

    @staticmethod
    def to_bridge_message(record: ConversationMessageRecord) -> dict[str, Any]:
        """Return the thread message JSON contract from a canonical record."""
        message: dict[str, Any] = {
            "role": record.role,
            "content": record.content,
        }
        if record.timestamp is not None:
            message["timestamp"] = record.timestamp.isoformat()
        if record.metadata_json:
            message["metadata"] = dict(record.metadata_json)
        blocks = [
            dict(block.payload_json or {})
            for block in sorted(record.blocks, key=lambda item: item.sequence_index)
        ]
        if blocks:
            message["blocks"] = blocks
        return message

    @staticmethod
    def to_thread_projection(thread: Thread) -> ConversationThreadProjection:
        """Return a DataService-owned thread summary projection."""
        return ConversationThreadProjection(
            id=str(thread.id),
            user_id=str(thread.user_id),
            workspace_id=str(thread.workspace_id) if thread.workspace_id else None,
            title=thread.title,
            model=thread.model,
            skill=thread.skill,
            message_count=int(thread.message_count or 0),
            last_message_preview=thread.last_message_preview,
            last_message_role=thread.last_message_role,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
