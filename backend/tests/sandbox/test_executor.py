"""Tests for sandbox execution environment."""

import pytest

from src.sandbox.executor import ExecutionResult, SandboxConfig, SandboxExecutor


class TestSandboxConfig:
    def test_create_config(self):
        """Should create sandbox configuration."""
        config = SandboxConfig(
            timeout=30,
            max_memory_mb=512,
        )
        assert config.timeout == 30
        assert config.max_memory_mb == 512

    def test_default_config(self):
        """Should have sensible defaults."""
        config = SandboxConfig()
        assert config.timeout == 30
        assert config.max_memory_mb == 256


class TestExecutionResult:
    def test_success_result(self):
        """Should create successful result."""
        result = ExecutionResult(
            success=True,
            output="hello\n",
            error=None,
        )
        assert result.success
        assert result.output == "hello\n"

    def test_failure_result(self):
        """Should create failure result."""
        result = ExecutionResult(
            success=False,
            output="",
            error="Error: something failed",
        )
        assert not result.success
        assert result.error is not None


class TestSandboxExecutor:
    @pytest.mark.asyncio
    async def test_execute_simple_code(self):
        """Should execute simple Python code."""
        executor = SandboxExecutor()
        result = await executor.execute("print('hello')")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_code_with_return(self):
        """Should capture return values."""
        executor = SandboxExecutor()
        result = await executor.execute("x = 1 + 2\nx")
        assert result.success
        assert "3" in result.output

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self):
        """Should enforce timeout on long-running code."""
        executor = SandboxExecutor(SandboxConfig(timeout=1))
        result = await executor.execute("import time; time.sleep(10)")
        assert not result.success
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_restricted_file_operations(self):
        """Should block dangerous file operations."""
        executor = SandboxExecutor()
        result = await executor.execute("open('/etc/passwd', 'r').read()")
        assert not result.success

    @pytest.mark.asyncio
    async def test_restricted_imports(self):
        """Should block dangerous imports."""
        executor = SandboxExecutor()
        result = await executor.execute("import subprocess; subprocess.run(['rm', '-rf', '/'])")
        assert not result.success

    @pytest.mark.asyncio
    async def test_restricted_os_operations(self):
        """Should block os.system calls."""
        executor = SandboxExecutor()
        result = await executor.execute("import os; os.system('echo hello')")
        assert not result.success

    @pytest.mark.asyncio
    async def test_syntax_error(self):
        """Should capture syntax errors."""
        executor = SandboxExecutor()
        result = await executor.execute("print('unclosed string")
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_runtime_error(self):
        """Should capture runtime errors."""
        executor = SandboxExecutor()
        result = await executor.execute("1/0")
        assert not result.success
        assert "ZeroDivisionError" in result.error or "division" in result.error.lower()
