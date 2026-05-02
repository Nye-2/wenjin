"""Runtime singleton dependencies (run manager, stream bridge)."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from src.runtime.runs import RunManager
from src.runtime.stream_bridge import StreamBridge


def get_run_manager(request: Request) -> RunManager:
    """Get the startup-initialized run manager singleton."""
    manager = getattr(request.app.state, "run_manager", None)
    if manager is None or not isinstance(manager, RunManager):
        raise RuntimeError(
            "Run runtime is not initialized. "
            "Gateway startup must create app.state.run_manager."
        )
    return cast(RunManager, manager)


def get_stream_bridge(request: Request) -> StreamBridge:
    """Get the startup-initialized stream bridge singleton."""
    bridge = getattr(request.app.state, "stream_bridge", None)
    if bridge is None or not isinstance(bridge, StreamBridge):
        raise RuntimeError(
            "Run stream bridge is not initialized. "
            "Gateway startup must create app.state.stream_bridge."
        )
    return cast(StreamBridge, bridge)
