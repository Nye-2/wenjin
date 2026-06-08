"""Per-workspace scheduling for harness sandbox tools."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import isawaitable
from typing import TypeVar

T = TypeVar("T")


class WorkspaceToolQueueTimeout(TimeoutError):
    """Raised when a workspace sandbox tool queue cannot be entered."""


@dataclass(slots=True)
class _WorkspaceLockEntry:
    lock: asyncio.Lock
    users: int = 0


class WorkspaceToolScheduler:
    """Serialize sandbox-affecting tool calls by workspace."""

    def __init__(self) -> None:
        self._locks: dict[str, _WorkspaceLockEntry] = {}
        self._guard = asyncio.Lock()

    async def run(
        self,
        workspace_id: str,
        operation: Callable[[], Awaitable[T] | T],
        *,
        timeout_seconds: float = 30,
    ) -> T:
        key = str(workspace_id)
        entry = await self._entry_for(key)
        acquired = False
        try:
            try:
                await asyncio.wait_for(entry.lock.acquire(), timeout=timeout_seconds)
                acquired = True
            except TimeoutError as exc:
                raise WorkspaceToolQueueTimeout(
                    f"workspace sandbox queue timed out: {workspace_id}"
                ) from exc
            value = operation()
            if isawaitable(value):
                return await value
            return value
        finally:
            if acquired:
                entry.lock.release()
            await self._release_entry(key, entry)

    async def _entry_for(self, key: str) -> _WorkspaceLockEntry:
        async with self._guard:
            entry = self._locks.get(key)
            if entry is None:
                entry = _WorkspaceLockEntry(lock=asyncio.Lock())
                self._locks[key] = entry
            entry.users += 1
            return entry

    async def _release_entry(self, key: str, entry: _WorkspaceLockEntry) -> None:
        async with self._guard:
            entry.users = max(0, entry.users - 1)
            if entry.users == 0 and not entry.lock.locked() and self._locks.get(key) is entry:
                self._locks.pop(key, None)


default_workspace_tool_scheduler = WorkspaceToolScheduler()
