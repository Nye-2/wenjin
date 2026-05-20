"""Conversation aggregate repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.conversation.block_protocol import (
    ConversationBlockKind,
    extract_invocation_ref,
    extract_tool_input,
    extract_tool_name,
    extract_tool_output,
)
from src.dataservice.domains.conversation.models import (
    MessageBlock,
    ThreadMessage,
    ToolInvocationRecord,
    ToolResultRecord,
)


class ConversationRepository:
    """Persistence operations for canonical conversation rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_message(
        self,
        *,
        thread_id: str,
        workspace_id: str | None,
        user_id: str,
        role: str,
        content: str,
        sequence_index: int,
        timestamp: Any | None,
        metadata_json: dict[str, Any],
        source_json: dict[str, Any],
    ) -> ThreadMessage:
        message = ThreadMessage(
            id=generate_uuid(),
            thread_id=thread_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            content=content,
            sequence_index=sequence_index,
            timestamp=timestamp,
            metadata_json=metadata_json,
            source_json=source_json,
        )
        self.session.add(message)
        return message

    def create_block(
        self,
        *,
        message_id: str,
        thread_id: str,
        block_type: str,
        sequence_index: int,
        payload_json: dict[str, Any],
    ) -> MessageBlock:
        block = MessageBlock(
            id=generate_uuid(),
            message_id=message_id,
            thread_id=thread_id,
            block_type=block_type,
            sequence_index=sequence_index,
            payload_json=payload_json,
        )
        self.session.add(block)
        if block_type == ConversationBlockKind.TOOL_INVOCATION.value:
            self.create_tool_invocation(block=block, payload=payload_json)
        elif block_type == ConversationBlockKind.TOOL_RESULT.value:
            self.create_tool_result(block=block, payload=payload_json)
        return block

    def create_tool_invocation(self, *, block: MessageBlock, payload: dict[str, Any]) -> ToolInvocationRecord:
        record = ToolInvocationRecord(
            id=generate_uuid(),
            block_id=block.id,
            thread_id=block.thread_id,
            message_id=block.message_id,
            invocation_ref=extract_invocation_ref(payload),
            tool_name=extract_tool_name(payload),
            status=str(payload.get("status")) if payload.get("status") is not None else None,
            input_json=extract_tool_input(payload),
        )
        self.session.add(record)
        return record

    def create_tool_result(self, *, block: MessageBlock, payload: dict[str, Any]) -> ToolResultRecord:
        record = ToolResultRecord(
            id=generate_uuid(),
            block_id=block.id,
            thread_id=block.thread_id,
            message_id=block.message_id,
            invocation_ref=extract_invocation_ref(payload),
            tool_name=extract_tool_name(payload),
            status=str(payload.get("status")) if payload.get("status") is not None else None,
            error=str(payload.get("error")) if payload.get("error") is not None else None,
            output_json=extract_tool_output(payload),
        )
        self.session.add(record)
        return record

    async def delete_thread_messages(self, thread_id: str) -> None:
        await self.session.execute(delete(ThreadMessage).where(ThreadMessage.thread_id == thread_id))

    async def list_messages(self, thread_id: str) -> list[ThreadMessage]:
        result = await self.session.execute(
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread_id)
            .order_by(ThreadMessage.sequence_index.asc())
        )
        return list(result.scalars().all())

    async def list_blocks_for_messages(self, message_ids: list[str]) -> list[MessageBlock]:
        if not message_ids:
            return []
        result = await self.session.execute(
            select(MessageBlock)
            .where(MessageBlock.message_id.in_(message_ids))
            .order_by(MessageBlock.message_id.asc(), MessageBlock.sequence_index.asc())
        )
        return list(result.scalars().all())
