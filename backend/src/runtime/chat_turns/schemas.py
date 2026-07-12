"""ChatTurnRun transport lifecycle enums."""

from enum import StrEnum


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
