"""Tests for LocalSandbox implementation."""

import os
import tempfile
from pathlib import Path

import pytest
from src.sandbox.base import FileInfo
from src.sandbox.providers.local import LocalSandbox, LocalSandboxProvider


class TestLocalSandbox:
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def sandbox(self, temp_dir):
        """Create LocalSandbox instance."""
        thread_dir = Path(temp_dir) / "thread-123"
        thread_dir.mkdir(parents=True)
        path_mappings = {
            "/mnt/user-data/workspace": str(thread_dir / "workspace"),
            "/mnt/user-data/uploads": str(thread_dir / "uploads"),
            "/mnt/user-data/outputs": str(thread_dir / "outputs"),
        }
        return LocalSandbox(id="thread-123", path_mappings=path_mappings)

    @pytest.mark.asyncio
    async def test_sandbox_id(self, sandbox):
        """Should return correct sandbox ID."""
        assert sandbox.sandbox_id == "thread-123"

    @pytest.mark.asyncio
    async def test_execute_command_echo(self, sandbox, temp_dir):
        """Should execute echo command."""
        result = await sandbox.execute_command("echo 'hello world'")
        assert result.success
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, sandbox):
        """Should handle command failure."""
        result = await sandbox.execute_command("ls /nonexistent_directory_12345")
        assert not result.success
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, sandbox, temp_dir):
        """Should write and read file through virtual path."""
        # Write file
        await sandbox.write_file(
            "/mnt/user-data/workspace/test.txt",
            "Hello, Sandbox!",
        )

        # Read file
        content = await sandbox.read_file("/mnt/user-data/workspace/test.txt")
        assert content == "Hello, Sandbox!"

    @pytest.mark.asyncio
    async def test_write_file_append(self, sandbox):
        """Should append to existing file."""
        await sandbox.write_file(
            "/mnt/user-data/workspace/append.txt",
            "Line 1\n",
        )
        await sandbox.write_file(
            "/mnt/user-data/workspace/append.txt",
            "Line 2\n",
            append=True,
        )

        content = await sandbox.read_file("/mnt/user-data/workspace/append.txt")
        assert "Line 1" in content
        assert "Line 2" in content

    @pytest.mark.asyncio
    async def test_list_dir(self, sandbox):
        """Should list directory contents."""
        # Create some files
        await sandbox.write_file("/mnt/user-data/workspace/file1.txt", "content1")
        await sandbox.write_file("/mnt/user-data/workspace/file2.txt", "content2")

        entries = await sandbox.list_dir("/mnt/user-data/workspace")
        assert len(entries) >= 2
        names = [e.name for e in entries]
        assert "file1.txt" in names
        assert "file2.txt" in names

    @pytest.mark.asyncio
    async def test_list_dir_with_subdirectory(self, sandbox):
        """Should list subdirectories."""
        await sandbox.write_file(
            "/mnt/user-data/workspace/subdir/file.txt",
            "content",
        )

        entries = await sandbox.list_dir("/mnt/user-data/workspace")
        subdir_entries = [e for e in entries if e.name == "subdir"]
        assert len(subdir_entries) == 1
        assert subdir_entries[0].is_dir

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, sandbox):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            await sandbox.read_file("/mnt/user-data/workspace/nonexistent.txt")

    @pytest.mark.asyncio
    async def test_command_timeout(self, sandbox):
        """Should timeout long-running commands."""
        result = await sandbox.execute_command("sleep 10", timeout=1)
        assert result.timed_out


class TestLocalSandboxProvider:
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def provider(self, temp_dir):
        """Create LocalSandboxProvider instance."""
        return LocalSandboxProvider(base_dir=temp_dir)

    @pytest.mark.asyncio
    async def test_acquire_sandbox(self, provider):
        """Should acquire a new sandbox."""
        sandbox = await provider.acquire("thread-456")
        assert sandbox.sandbox_id == "thread-456"

    @pytest.mark.asyncio
    async def test_get_existing_sandbox(self, provider):
        """Should get existing sandbox by ID."""
        sandbox1 = await provider.acquire("thread-789")
        sandbox2 = provider.get("thread-789")
        assert sandbox2 is not None
        assert sandbox2.sandbox_id == "thread-789"

    @pytest.mark.asyncio
    async def test_get_nonexistent_sandbox(self, provider):
        """Should return None for nonexistent sandbox."""
        sandbox = provider.get("nonexistent-id")
        assert sandbox is None

    @pytest.mark.asyncio
    async def test_release_sandbox(self, provider):
        """Should release sandbox."""
        await provider.acquire("thread-to-release")
        await provider.release(provider.get("thread-to-release"))

        # After release, sandbox should be removed
        sandbox = provider.get("thread-to-release")
        assert sandbox is None

    @pytest.mark.asyncio
    async def test_acquire_creates_directories(self, provider, temp_dir):
        """Should create thread directories on acquire."""
        await provider.acquire("thread-dirs")

        thread_path = Path(temp_dir) / "thread-dirs"
        assert thread_path.exists()
        assert (thread_path / "workspace").exists()
        assert (thread_path / "uploads").exists()
        assert (thread_path / "outputs").exists()
