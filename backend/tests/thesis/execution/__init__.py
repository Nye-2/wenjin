# tests/thesis/execution/__init__.py
"""Tests for thesis execution tools.

Provides reusable fixtures for mocking ExecutionService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from src.execution.types import ExecutionResult, ExecutionStatus


@pytest.fixture
def mock_execution_result() -> MagicMock:
    """Create a basic mock execution result.

    Returns:
        MagicMock with success status and default values
    """
    result = MagicMock()
    result.status = MagicMock()
    result.status.value = "success"
    result.sandbox_path = "/sandbox/test/output.pdf"
    result.metadata = {}
    result.logs = ""
    result.error_message = None
    return result


@pytest.fixture
def mock_execution_service(mock_execution_result: MagicMock) -> MagicMock:
    """Create a mock ExecutionService.

    Args:
        mock_execution_result: The result to return from execute()

    Returns:
        MagicMock with execute() method
    """
    service = MagicMock()
    service.execute = AsyncMock(return_value=mock_execution_result)
    service.health_check = AsyncMock(return_value={"status": "healthy"})
    return service


def create_mock_result(
    status: str = "success",
    sandbox_path: str | None = "/sandbox/test/output.pdf",
    metadata: dict | None = None,
    error_message: str | None = None,
) -> MagicMock:
    """Create a mock execution result with custom values.

    Args:
        status: Execution status ("success" or "failed")
        sandbox_path: Output file path
        metadata: Result metadata dict
        error_message: Error message if failed

    Returns:
        MagicMock configured with the specified values
    """
    result = MagicMock()
    result.status = MagicMock()
    result.status.value = status
    result.sandbox_path = sandbox_path
    result.metadata = metadata or {}
    result.logs = ""
    result.error_message = error_message
    return result


__all__ = [
    "mock_execution_result",
    "mock_execution_service",
    "create_mock_result",
]