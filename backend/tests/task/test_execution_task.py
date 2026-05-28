"""Tests for execution worker task guards."""

from __future__ import annotations

from src.task.tasks.execution import is_terminal_execution_status


def test_failed_execution_status_is_terminal_for_worker_redelivery():
    assert is_terminal_execution_status("failed")
    assert is_terminal_execution_status("completed")
    assert is_terminal_execution_status("cancelled")
    assert not is_terminal_execution_status("running")
