"""Conversation projection helpers."""

from __future__ import annotations

from src.dataservice.domains.conversation.contracts import ConversationMessageRecord
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage
from src.dataservice.domains.conversation.service import DataServiceConversationService


def conversation_message_to_record(
    message: ThreadMessage,
    *,
    blocks: list[MessageBlock],
) -> ConversationMessageRecord:
    """Return canonical message projection."""
    return DataServiceConversationService.to_message_record(message, blocks=blocks)
