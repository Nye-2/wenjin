# tests/sandbox/test_exceptions.py
"""Tests for sandbox exceptions."""

import pytest
from src.sandbox.exceptions import (
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
)


class TestSandboxExceptions:
    def test_base_exception(self):
        """Should create base sandbox error."""
        error = SandboxError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_not_found_error(self):
        """Should create not found error with sandbox_id."""
        error = SandboxNotFoundError("Sandbox not found", sandbox_id="test-123")
        assert "test-123" in str(error)
        assert error.sandbox_id == "test-123"

    def test_runtime_error(self):
        """Should create runtime error with details."""
        error = SandboxRuntimeError("Execution failed", command="ls -la")
        assert "Execution failed" in str(error)
        assert error.command == "ls -la"

    def test_timeout_error(self):
        """Should create timeout error with duration."""
        error = SandboxTimeoutError("Command timed out", timeout=30)
        assert "30" in str(error)
        assert error.timeout == 30

    def test_inheritance_chain(self):
        """Should have correct inheritance."""
        assert issubclass(SandboxNotFoundError, SandboxError)
        assert issubclass(SandboxRuntimeError, SandboxError)
        assert issubclass(SandboxTimeoutError, SandboxRuntimeError)
