"""Conversation aggregate command service."""

from __future__ import annotations

import copy
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
    ConversationAttachmentStatePatchCommand,
    ConversationBlockRecord,
    ConversationMessageCreateCommand,
    ConversationMessageRecord,
    ConversationThreadCreateCommand,
    ConversationThreadProjection,
    ConversationThreadUpdateCommand,
)
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage
from src.dataservice.domains.conversation.repository import ConversationRepository

_LAST_MESSAGE_PREVIEW_LIMIT = 120


def _truncate_message_preview(content: str | None, limit: int = _LAST_MESSAGE_PREVIEW_LIMIT) -> str | None:
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


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
                "message_count": 0,
                "last_message_preview": None,
                "last_message_role": None,
                "created_at": command.created_at or now,
                "updated_at": command.updated_at or command.created_at or now,
            }
        )
        await self._finish()
        return self.to_thread_projection(thread)

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

    async def append_message(self, command: ConversationMessageCreateCommand) -> ThreadMessage:
        message, _ = await self._append_message_locked(command, card_id=None)
        return message

    async def append_card_message(
        self,
        command: ConversationMessageCreateCommand,
        *,
        card_id: str,
    ) -> tuple[ThreadMessage, bool]:
        """Append one card message unless ``card_id`` already exists in the thread.

        Returns the persisted message and whether it was newly appended.
        """
        return await self._append_message_locked(command, card_id=card_id)

    async def _append_message_locked(
        self,
        command: ConversationMessageCreateCommand,
        *,
        card_id: str | None,
    ) -> tuple[ThreadMessage, bool]:
        await self.repository.lock_thread(command.thread_id)
        if card_id:
            existing = await self.repository.find_message_by_card_id(
                thread_id=command.thread_id,
                card_id=card_id,
            )
            if existing is not None:
                return existing, False
        thread = await self.repository.get_thread(command.thread_id)
        sequence_index = await self.repository.next_message_sequence(command.thread_id)
        metadata = dict(command.metadata or {})
        if card_id:
            metadata.setdefault("card_id", card_id)
        message = self.repository.create_message(
            thread_id=command.thread_id,
            workspace_id=command.workspace_id,
            user_id=command.user_id,
            role=command.role,
            content=command.content,
            sequence_index=sequence_index,
            timestamp=command.timestamp,
            metadata_json=metadata,
            source_json=dict(command.source_json or {}),
        )
        raw_blocks = command.blocks or blocks_from_message(
            {
                "content": command.content,
                "blocks": command.blocks,
            }
        )
        await self.session.flush()
        for index, block in enumerate(raw_blocks):
            payload = normalize_block_payload(block) if isinstance(block, Mapping) else {}
            self.repository.create_block(
                message_id=message.id,
                thread_id=command.thread_id,
                block_type=canonical_block_kind(payload),
                sequence_index=index,
                payload_json=payload,
            )
        if thread is not None:
            normalized_role = str(command.role).strip()
            thread.message_count = sequence_index + 1
            thread.last_message_role = normalized_role or None
            thread.last_message_preview = _truncate_message_preview(command.content)
            thread.updated_at = command.timestamp or datetime.now(UTC)
        await self._finish()
        return message, True

    async def patch_attachment_state(
        self,
        command: ConversationAttachmentStatePatchCommand,
    ) -> bool:
        """Patch attachment state under the same thread lock used by chat writes."""
        await self.repository.lock_thread(command.thread_id)
        thread = await self.repository.get_thread(command.thread_id)
        if thread is None:
            return False

        changed = False
        for persisted in await self.repository.list_messages(command.thread_id):
            metadata = copy.deepcopy(dict(persisted.metadata_json or {}))
            attachments = metadata.get("attachments")
            if not isinstance(attachments, list):
                continue
            message_changed = False
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                attachment_metadata = attachment.get("metadata")
                if not isinstance(attachment_metadata, dict):
                    continue
                current_state = attachment_metadata.get(command.state_key)
                if (
                    not isinstance(current_state, dict)
                    or current_state.get("task_id") != command.task_id
                ):
                    continue

                next_state = dict(current_state)
                next_state.update(command.state_patch)
                next_state["task_id"] = command.task_id
                if (
                    command.state_key == "preprocess"
                    and command.status == "success"
                ):
                    next_state["status"] = str(
                        command.state_patch.get("status")
                        or next_state.get("status")
                        or "succeeded"
                    )
                else:
                    next_state["status"] = command.status
                if command.message:
                    next_state["message"] = command.message
                if command.progress is not None:
                    next_state["progress"] = command.progress
                if command.current_step:
                    next_state["current_step"] = command.current_step
                elif command.current_step == "":
                    next_state.pop("current_step", None)
                if command.error:
                    next_state["error"] = command.error
                    if command.state_key == "preprocess":
                        next_state["status"] = "failed"
                elif next_state.get("status") in {"success", "succeeded"}:
                    next_state.pop("error", None)

                attachment_metadata[command.state_key] = next_state
                message_changed = True

            if message_changed:
                persisted.metadata_json = metadata
                changed = True

        if changed:
            thread.updated_at = datetime.now(UTC)
            await self._finish()
        return changed

    async def list_message_records(self, thread_id: str) -> list[ConversationMessageRecord]:
        messages = await self.repository.list_messages(thread_id)
        return await self._message_records(messages)

    async def _message_records(
        self,
        messages: list[ThreadMessage],
    ) -> list[ConversationMessageRecord]:
        blocks = await self.repository.list_blocks_for_messages([message.id for message in messages])
        blocks_by_message: dict[str, list[MessageBlock]] = {}
        for block in blocks:
            blocks_by_message.setdefault(block.message_id, []).append(block)
        return [
            self.to_message_record(message, blocks=blocks_by_message.get(message.id, []))
            for message in messages
        ]

    async def get_message_record(
        self,
        message_id: str,
    ) -> ConversationMessageRecord | None:
        message = await self.repository.get_message(message_id)
        if message is None:
            return None
        blocks = await self.repository.list_blocks_for_messages([message_id])
        return self.to_message_record(message, blocks=blocks)

    async def delete_trailing_user_message(
        self,
        *,
        thread_id: str,
        user_id: str,
        expected_message_id: str,
    ) -> bool:
        """Delete exactly one authorized trailing user turn under the thread lock."""
        await self.repository.lock_thread(thread_id)
        thread = await self.repository.get_owned_thread(
            thread_id=thread_id,
            user_id=user_id,
        )
        if thread is None:
            return False
        message = await self.repository.get_last_message(thread_id)
        if (
            message is None
            or str(message.id) != expected_message_id
            or message.role != "user"
            or str(message.user_id) != user_id
        ):
            return False

        await self.repository.delete_message(message)
        await self.session.flush()
        previous = await self.repository.get_last_message(thread_id)
        thread.message_count = int(previous.sequence_index) + 1 if previous else 0
        thread.last_message_role = previous.role if previous else None
        thread.last_message_preview = (
            _truncate_message_preview(previous.content) if previous else None
        )
        thread.updated_at = datetime.now(UTC)
        await self._finish()
        return True

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

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

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
            message_count=int(thread.message_count or 0),
            last_message_preview=thread.last_message_preview,
            last_message_role=thread.last_message_role,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
