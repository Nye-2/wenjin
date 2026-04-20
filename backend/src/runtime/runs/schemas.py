"""Run lifecycle enums."""

from enum import StrEnum


class RunStatus(StrEnum):
    """Lifecycle status for one run."""

    pending = "pending"
    running = "running"
    success = "success"
    error = "error"
    interrupted = "interrupted"


class DisconnectMode(StrEnum):
    """What to do when SSE subscriber disconnects."""

    cancel = "cancel"
    continue_ = "continue"
