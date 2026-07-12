"""Short-lived ChatTurnRun transport dependencies."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from src.runtime.chat_turns import ChatTurnRunManager
from src.runtime.stream_bridge import StreamBridge


def get_chat_turn_run_manager(request: Request) -> ChatTurnRunManager:
    """Get the startup-initialized run manager singleton."""
    manager = getattr(request.app.state, "chat_turn_run_manager", None)
    if manager is None or not isinstance(manager, ChatTurnRunManager):
        raise RuntimeError("ChatTurnRun transport is not initialized. Gateway startup must create app.state.chat_turn_run_manager.")
    return cast(ChatTurnRunManager, manager)


def get_chat_turn_stream_bridge(request: Request) -> StreamBridge:
    """Get the startup-initialized stream bridge singleton."""
    bridge = getattr(request.app.state, "chat_turn_stream_bridge", None)
    if bridge is None or not isinstance(bridge, StreamBridge):
        raise RuntimeError("ChatTurnRun stream bridge is not initialized. Gateway startup must create app.state.chat_turn_stream_bridge.")
    return cast(StreamBridge, bridge)
