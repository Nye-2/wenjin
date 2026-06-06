"""Per-workspace scheduling for harness sandbox tools."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import TypeVar

T = TypeVar("T")


class WorkspaceToolQueueTimeout(TimeoutError):
    """Raised when a workspace sandbox tool queue cannot be entered."""


class WorkspaceToolScheduler:
    """Serialize sandbox-affecting tool calls by workspace."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def run(
        self,
        workspace_id: str,
        operation: Callable[[], Awaitable[T] | T],
        *,
        timeout_seconds: float = 30,
    ) -> T:
        lock = await self._lock_for(workspace_id)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise WorkspaceToolQueueTimeout(
                f"workspace sandbox queue timed out: {workspace_id}"
            ) from exc
        try:
            value = operation()
            if isawaitable(value):
                return await value
            return value
        finally:
            lock.release()

    async def _lock_for(self, workspace_id: str) -> asyncio.Lock:
        key = str(workspace_id)
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock


default_workspace_tool_scheduler = WorkspaceToolScheduler()
