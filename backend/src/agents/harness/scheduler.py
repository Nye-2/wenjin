"""Per-workspace scheduling for harness sandbox tools."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Literal, TypeVar

T = TypeVar("T")
WorkspaceToolMode = Literal["read", "write"]


class WorkspaceToolQueueTimeout(TimeoutError):
    """Raised when a workspace sandbox tool queue cannot be entered."""


@dataclass(slots=True)
class _WorkspaceLockEntry:
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    users: int = 0
    active_readers: int = 0
    writer_active: bool = False
    waiting_writers: int = 0


class WorkspaceToolScheduler:
    """Coordinate sandbox-affecting tool calls by workspace.

    Reads may run concurrently. Writes and execution jobs stay exclusive so
    workspace filesystem mutations remain ordered and reproducible.
    """

    def __init__(self) -> None:
        self._locks: dict[str, _WorkspaceLockEntry] = {}
        self._guard = asyncio.Lock()

    async def run(
        self,
        workspace_id: str,
        operation: Callable[[], Awaitable[T] | T],
        *,
        timeout_seconds: float = 30,
        mode: WorkspaceToolMode = "write",
    ) -> T:
        if mode not in {"read", "write"}:
            raise ValueError(f"unsupported workspace tool scheduler mode: {mode}")
        key = str(workspace_id)
        entry = await self._entry_for(key)
        acquired = False
        try:
            try:
                await asyncio.wait_for(self._acquire(entry, mode), timeout=timeout_seconds)
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
                await self._release(entry, mode)
            await self._release_entry(key, entry)

    async def _entry_for(self, key: str) -> _WorkspaceLockEntry:
        async with self._guard:
            entry = self._locks.get(key)
            if entry is None:
                entry = _WorkspaceLockEntry()
                self._locks[key] = entry
            entry.users += 1
            return entry

    async def _acquire(self, entry: _WorkspaceLockEntry, mode: WorkspaceToolMode) -> None:
        if mode == "read":
            async with entry.condition:
                await entry.condition.wait_for(
                    lambda: not entry.writer_active and entry.waiting_writers == 0
                )
                entry.active_readers += 1
            return

        async with entry.condition:
            entry.waiting_writers += 1
            try:
                await entry.condition.wait_for(
                    lambda: not entry.writer_active and entry.active_readers == 0
                )
                entry.writer_active = True
            finally:
                entry.waiting_writers = max(0, entry.waiting_writers - 1)

    async def _release(self, entry: _WorkspaceLockEntry, mode: WorkspaceToolMode) -> None:
        async with entry.condition:
            if mode == "read":
                entry.active_readers = max(0, entry.active_readers - 1)
            else:
                entry.writer_active = False
            entry.condition.notify_all()

    async def _release_entry(self, key: str, entry: _WorkspaceLockEntry) -> None:
        async with self._guard:
            entry.users = max(0, entry.users - 1)
            if (
                entry.users == 0
                and entry.active_readers == 0
                and not entry.writer_active
                and entry.waiting_writers == 0
                and self._locks.get(key) is entry
            ):
                self._locks.pop(key, None)


default_workspace_tool_scheduler = WorkspaceToolScheduler()
