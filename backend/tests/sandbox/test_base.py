"""Tests for sandbox base classes."""

import pytest

from src.sandbox.base import CommandResult, FileInfo, Sandbox


class TestCommandResult:
    def test_success_result(self):
        """Should create successful command result."""
        result = CommandResult(
            stdout="hello\n",
            stderr="",
            exit_code=0,
        )
        assert result.success
        assert result.stdout == "hello\n"
        assert result.exit_code == 0

    def test_failure_result(self):
        """Should create failed command result."""
        result = CommandResult(
            stdout="",
            stderr="command not found",
            exit_code=127,
        )
        assert not result.success
        assert result.stderr == "command not found"

    def test_timeout_result(self):
        """Should create timed out result."""
        result = CommandResult(
            stdout="partial output",
            stderr="",
            exit_code=-1,
            timed_out=True,
        )
        assert result.timed_out
        assert not result.success

    def test_default_values(self):
        """Should have sensible defaults."""
        result = CommandResult(stdout="ok", stderr="", exit_code=0)
        assert result.timed_out is False


class TestFileInfo:
    def test_file_info(self):
        """Should create file info."""
        info = FileInfo(
            name="test.txt",
            path="/mnt/user-data/workspace/test.txt",
            is_dir=False,
            size=1024,
        )
        assert info.name == "test.txt"
        assert info.is_dir is False
        assert info.size == 1024

    def test_directory_info(self):
        """Should create directory info."""
        info = FileInfo(
            name="src",
            path="/mnt/user-data/workspace/src",
            is_dir=True,
        )
        assert info.is_dir
        assert info.size is None


class TestSandboxInterface:
    def test_sandbox_is_abstract(self):
        """Should not be able to instantiate Sandbox directly."""
        with pytest.raises(TypeError):
            Sandbox(id="test")

    def test_sandbox_has_required_methods(self):
        """Should have all required abstract methods."""
        methods = ["execute_command", "read_file", "write_file", "list_dir", "sandbox_id"]
        for method in methods:
            assert hasattr(Sandbox, method) or method in dir(Sandbox)
