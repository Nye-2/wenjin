"""ChatTurnRun transport lifecycle enums."""

import hashlib
from enum import StrEnum


def chat_turn_idempotency_key(
    request_id: str,
    *,
    actor_id: str,
) -> str:
    """Build the actor-global identity carried across worker dispatch."""
    normalized_request_id = str(request_id).strip()
    normalized_actor_id = str(actor_id).strip()
    if not normalized_request_id:
        raise ValueError("chat-turn request_id must not be empty")
    if not normalized_actor_id:
        raise ValueError("chat-turn actor_id must not be empty")
    digest = hashlib.sha256(
        f"{normalized_actor_id}\0{normalized_request_id}".encode()
    ).hexdigest()
    return f"chat-turn:{digest}"


class ChatTurnRunStatus(StrEnum):
    """Lifecycle status for one run."""

    pending = "pending"
    running = "running"
    success = "success"
    error = "error"
    interrupted = "interrupted"


class ChatTurnDisconnectMode(StrEnum):
    """What to do when SSE subscriber disconnects."""

    cancel = "cancel"
    continue_ = "continue"


class ChatTurnExecutionRenewal(StrEnum):
    """Result of renewing a fenced worker execution lease."""

    renewed = "renewed"
    retryable = "retryable"
    lost = "lost"
