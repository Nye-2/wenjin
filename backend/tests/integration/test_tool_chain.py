"""Integration tests for tool chain execution.

This module tests that various tools work together in skill execution chains:
- SandboxExecutor executes code safely
- Tools can be chained together
"""

import pytest


class TestSandboxInSkill:
    """Tests for sandbox being used within skills."""

    @pytest.mark.asyncio
    async def test_sandbox_executes_code(self):
        """Sandbox should execute code safely."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("x = 1 + 1; print(x)")
        assert result.success
        assert "2" in result.output

    @pytest.mark.asyncio
    async def test_sandbox_executes_complex_code(self):
        """Sandbox should execute more complex Python code."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("""
import math
result = sum([i**2 for i in range(5)])
print(f"Sum of squares: {result}")
""")
        assert result.success
        assert "30" in result.output  # 0+1+4+9+16 = 30

    @pytest.mark.asyncio
    async def test_sandbox_blocks_dangerous_code(self):
        """Sandbox should block dangerous operations."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("import subprocess")
        assert not result.success

    @pytest.mark.asyncio
    async def test_sandbox_blocks_os_system(self):
        """Sandbox should block os.system calls."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("import os; os.system('ls')")
        assert not result.success

    @pytest.mark.asyncio
    async def test_sandbox_allows_safe_imports(self):
        """Sandbox should allow safe module imports."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("""
import math
import json
import statistics
print(math.sqrt(16))
""")
        assert result.success
        assert "4" in result.output

    @pytest.mark.asyncio
    async def test_sandbox_handles_syntax_error(self):
        """Sandbox should handle syntax errors gracefully."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()
        result = await executor.execute("this is not valid python")

        assert not result.success
        assert result.error is not None
        assert "SyntaxError" in result.error


class TestFullToolChain:
    """Tests for complete tool chain execution."""

    @pytest.mark.asyncio
    async def test_search_to_analysis_chain(self):
        """Should chain prepared data -> sandbox analysis."""
        from src.sandbox.executor import SandboxExecutor

        sandbox = SandboxExecutor()
        result = await sandbox.execute("""
papers = ["Paper 1", "Paper 2", "Paper 3"]
count = len(papers)
print(f"Found {count} papers")
""")

        assert result.success
        assert "3" in result.output

    @pytest.mark.asyncio
    async def test_tool_chain_with_multiple_steps(self):
        """Should execute a multi-step tool chain."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()

        # Step 1: Data processing
        step1_result = await executor.execute("""
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
mean_val = sum(data) / len(data)
print(f"Mean: {mean_val}")
""")

        assert step1_result.success
        assert "5.5" in step1_result.output

        # Step 2: Further analysis
        step2_result = await executor.execute("""
import statistics
values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
median_val = statistics.median(values)
print(f"Median: {median_val}")
""")

        assert step2_result.success
        assert "5.5" in step2_result.output


class TestToolChainPerformance:
    """Tests for tool chain performance."""

    @pytest.mark.asyncio
    async def test_sandbox_completes_quickly(self):
        """Sandbox operations should complete quickly."""
        import time

        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()

        start = time.time()
        result = await executor.execute("""
total = sum(range(1000))
print(f"Total: {total}")
""")
        elapsed = time.time() - start

        assert result.success
        assert elapsed < 5.0, f"Sandbox took {elapsed:.2f}s (limit: 5s)"


class TestToolChainErrorRecovery:
    """Tests for error recovery in tool chains."""

    @pytest.mark.asyncio
    async def test_chain_continues_after_sandbox_error(self):
        """Tool chain should continue after sandbox error."""
        from src.sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()

        # First execution fails
        result1 = await executor.execute("import subprocess")
        assert not result1.success

        # Second execution should still work
        result2 = await executor.execute("print('hello')")
        assert result2.success
        assert "hello" in result2.output

    @pytest.mark.asyncio
    async def test_chain_handles_timeout_gracefully(self):
        """Chain should handle sandbox timeout gracefully."""
        from src.sandbox.executor import SandboxConfig, SandboxExecutor

        # Very short timeout
        config = SandboxConfig(timeout=1)
        executor = SandboxExecutor(config=config)

        # This should timeout
        result = await executor.execute("""
import time
time.sleep(10)  # Sleep longer than timeout
print("Should not reach here")
""")

        assert not result.success
        assert "timeout" in result.error.lower()
