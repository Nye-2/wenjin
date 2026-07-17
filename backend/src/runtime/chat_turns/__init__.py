"""Short-lived ChatTurnRun transport primitives."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .manager import (
    ChatTurnConflictError,
    ChatTurnRunAdmission,
    ChatTurnRunManager,
    ChatTurnRunRecord,
    ChatTurnTransportUnavailableError,
    UnsupportedChatTurnStrategyError,
)
from .schemas import (
    ChatTurnDisconnectMode,
    ChatTurnExecutionRenewal,
    ChatTurnRunStatus,
)

__all__ = [
    "ChatTurnConflictError",
    "ChatTurnDisconnectMode",
    "ChatTurnExecutionRenewal",
    "ChatTurnRunAdmission",
    "ChatTurnRunManager",
    "ChatTurnRunRecord",
    "ChatTurnRunStatus",
    "ChatTurnTransportUnavailableError",
    "UnsupportedChatTurnStrategyError",
    "run_chat_turn",
]


def __getattr__(name: str) -> Any:
    if name != "run_chat_turn":
        raise AttributeError(name)
    value = getattr(import_module("src.runtime.chat_turns.worker"), name)
    globals()[name] = value
    return value
