"""Per-sandbox file operation lock registry."""

from __future__ import annotations

import asyncio
import threading
import weakref

from src.sandbox.base import Sandbox

_LockKey = tuple[str, str]
_FILE_OPERATION_LOCKS: weakref.WeakValueDictionary[_LockKey, asyncio.Lock] = weakref.WeakValueDictionary()
_FILE_OPERATION_LOCKS_GUARD = threading.Lock()


def get_file_operation_lock_key(sandbox: Sandbox, path: str) -> _LockKey:
    """Build a stable lock key from sandbox id and normalized path."""
    sandbox_id = getattr(sandbox, "sandbox_id", None)
    if not sandbox_id:
        sandbox_id = f"instance:{id(sandbox)}"
    return str(sandbox_id), str(path)


def get_file_operation_lock(sandbox: Sandbox, path: str) -> asyncio.Lock:
    """Get (or create) an asyncio lock for a sandbox-scoped path."""
    lock_key = get_file_operation_lock_key(sandbox, path)
    with _FILE_OPERATION_LOCKS_GUARD:
        lock = _FILE_OPERATION_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _FILE_OPERATION_LOCKS[lock_key] = lock
        return lock
