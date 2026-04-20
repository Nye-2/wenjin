"""Tests for per-sandbox file operation locks."""

from __future__ import annotations

from src.sandbox.file_operation_lock import (
    get_file_operation_lock,
    get_file_operation_lock_key,
)


class _SandboxStub:
    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id


def test_get_file_operation_lock_reuses_same_lock_for_same_path():
    sandbox = _SandboxStub("thread-1")
    lock_a = get_file_operation_lock(sandbox, "/mnt/user-data/workspace/a.txt")
    lock_b = get_file_operation_lock(sandbox, "/mnt/user-data/workspace/a.txt")
    assert lock_a is lock_b


def test_get_file_operation_lock_uses_distinct_keys_for_distinct_paths():
    sandbox = _SandboxStub("thread-1")
    lock_a = get_file_operation_lock(sandbox, "/mnt/user-data/workspace/a.txt")
    lock_b = get_file_operation_lock(sandbox, "/mnt/user-data/workspace/b.txt")
    assert lock_a is not lock_b


def test_get_file_operation_lock_key_falls_back_to_instance_id():
    class _NoSandboxId:
        pass

    key = get_file_operation_lock_key(_NoSandboxId(), "/tmp/path")
    assert key[0].startswith("instance:")
    assert key[1] == "/tmp/path"
