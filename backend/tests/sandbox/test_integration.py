"""Integration tests for sandbox system."""

import tempfile
from pathlib import Path

import pytest

from src.sandbox import (
    LocalSandboxProvider,
    SandboxSettings,
    VirtualPathMapper,
)


class TestSandboxIntegration:
    """End-to-end integration tests."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_dir):
        """Test complete sandbox workflow from acquire to release."""
        # 1. Create provider
        provider = LocalSandboxProvider(base_dir=temp_dir)

        # 2. Acquire sandbox
        sandbox = await provider.acquire("integration-test")
        assert sandbox.sandbox_id == "integration-test"

        # 3. Execute command
        result = await sandbox.execute_command("echo 'Integration Test'")
        assert result.success
        assert "Integration Test" in result.stdout

        # 4. Write file
        await sandbox.write_file(
            "/mnt/user-data/workspace/document.tex",
            r"\documentclass{article}\begin{document}Test\end{document}",
        )

        # 5. Read file back
        content = await sandbox.read_file("/mnt/user-data/workspace/document.tex")
        assert "documentclass" in content

        # 6. List directory
        entries = await sandbox.list_dir("/mnt/user-data/workspace")
        names = [e.name for e in entries]
        assert "document.tex" in names

        # 7. Verify physical files exist
        physical_path = Path(temp_dir) / "integration-test" / "workspace" / "document.tex"
        assert physical_path.exists()

        # 8. Release sandbox
        await provider.release(sandbox)

        # 9. Verify sandbox is removed
        assert provider.get("integration-test") is None

    @pytest.mark.asyncio
    async def test_multiple_threads_isolation(self, temp_dir):
        """Test that threads are isolated from each other."""
        provider = LocalSandboxProvider(base_dir=temp_dir)

        # Create sandboxes for two threads
        sandbox1 = await provider.acquire("thread-1")
        sandbox2 = await provider.acquire("thread-2")

        # Write different content to each
        await sandbox1.write_file("/mnt/user-data/workspace/file.txt", "Thread 1")
        await sandbox2.write_file("/mnt/user-data/workspace/file.txt", "Thread 2")

        # Verify isolation
        content1 = await sandbox1.read_file("/mnt/user-data/workspace/file.txt")
        content2 = await sandbox2.read_file("/mnt/user-data/workspace/file.txt")

        assert content1 == "Thread 1"
        assert content2 == "Thread 2"

        # Cleanup
        await provider.release(sandbox1)
        await provider.release(sandbox2)

    @pytest.mark.asyncio
    async def test_path_mapper_integration(self, temp_dir):
        """Test VirtualPathMapper with provider."""
        provider = LocalSandboxProvider(base_dir=temp_dir)
        sandbox = await provider.acquire("path-test")

        mapper = VirtualPathMapper(base_dir=temp_dir)

        # Test path conversion
        virtual = "/mnt/user-data/workspace/test.txt"
        physical = mapper.to_physical(virtual, thread_id="path-test")

        assert "path-test/workspace/test.txt" in physical

        # Cleanup
        await provider.release(sandbox)

    @pytest.mark.asyncio
    async def test_settings_integration(self):
        """Test SandboxSettings with default values."""
        settings = SandboxSettings()

        assert settings.mode == "local"
        assert settings.local.base_dir == ".academiagpt/threads"
        assert settings.academic.latex.enabled is True
        assert "python" in settings.academic.code_execution.languages

    @pytest.mark.asyncio
    async def test_command_with_virtual_path(self, temp_dir):
        """Test command execution with virtual path translation."""
        provider = LocalSandboxProvider(base_dir=temp_dir)
        sandbox = await provider.acquire("cmd-test")

        # Create a file
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "Hello")

        # Use command with virtual path
        result = await sandbox.execute_command("cat /mnt/user-data/workspace/test.txt")
        assert "Hello" in result.stdout

        await provider.release(sandbox)

    @pytest.mark.asyncio
    async def test_sandbox_reuse(self, temp_dir):
        """Test that acquiring same thread returns same sandbox."""
        provider = LocalSandboxProvider(base_dir=temp_dir)

        sandbox1 = await provider.acquire("reuse-test")
        sandbox2 = await provider.acquire("reuse-test")

        assert sandbox1 is sandbox2

        await provider.release(sandbox1)


class TestErrorHandling:
    """Test error handling across components."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir):
        """Test error when reading nonexistent file."""
        provider = LocalSandboxProvider(base_dir=temp_dir)
        sandbox = await provider.acquire("error-test")

        with pytest.raises(FileNotFoundError):
            await sandbox.read_file("/mnt/user-data/workspace/nonexistent.txt")

        await provider.release(sandbox)

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self, temp_dir):
        """Test error when listing nonexistent directory."""
        provider = LocalSandboxProvider(base_dir=temp_dir)
        sandbox = await provider.acquire("error-test-2")

        with pytest.raises(FileNotFoundError):
            await sandbox.list_dir("/mnt/user-data/workspace/nonexistent")

        await provider.release(sandbox)

    @pytest.mark.asyncio
    async def test_command_timeout(self, temp_dir):
        """Test command timeout handling."""
        provider = LocalSandboxProvider(base_dir=temp_dir)
        sandbox = await provider.acquire("timeout-test")

        result = await sandbox.execute_command("sleep 10", timeout=1)
        assert result.timed_out

        await provider.release(sandbox)