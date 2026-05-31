"""Tests for LocalSandbox implementation."""

import tempfile
from pathlib import Path

import pytest

from src.sandbox.providers.local import (
    LocalSandbox,
    LocalSandboxProvider,
    SandboxSecurityError,
)


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
        user_data_dir = thread_dir / "user-data"
        user_data_dir.mkdir(parents=True)
        path_mappings = {
            "/mnt/user-data/workspace": str(user_data_dir / "workspace"),
            "/mnt/user-data/uploads": str(user_data_dir / "uploads"),
            "/mnt/user-data/outputs": str(user_data_dir / "outputs"),
        }
        for mapped_path in path_mappings.values():
            Path(mapped_path).mkdir(parents=True, exist_ok=True)
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

    def test_allows_workspace_virtual_paths(self, temp_dir):
        """Should support the canonical workspace sandbox mount."""
        workspace = Path(temp_dir) / "workspace"
        workspace.mkdir(parents=True)
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})

        resolved = sandbox._resolve_path("/workspace/analysis.py")

        assert resolved.endswith("analysis.py")

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

    @pytest.mark.asyncio
    async def test_execute_command_rejects_host_absolute_paths(self, sandbox):
        """Shell commands should not reference host absolute paths directly."""
        result = await sandbox.execute_command("cat /etc/hosts")
        assert not result.success
        assert "outside sandbox" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_command_rejects_unmapped_workspace_root(self, sandbox):
        """Virtual roots are only allowed when this sandbox mapped them."""
        result = await sandbox.execute_command("cat /workspace/analysis.py")
        assert not result.success
        assert "outside sandbox" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_command_rejects_relative_escape_paths(self, sandbox, temp_dir):
        """Shell commands should not escape the sandbox via relative traversal."""
        Path(temp_dir, "secret.txt").write_text("host-secret", encoding="utf-8")

        result = await sandbox.execute_command("cat ../../../secret.txt")

        assert not result.success
        assert "outside sandbox" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_command_allows_relative_paths_within_user_data(self, sandbox):
        """Relative traversal to sibling sandbox dirs should remain available."""
        await sandbox.write_file("/mnt/user-data/uploads/input.txt", "upload-data")

        result = await sandbox.execute_command("cat ../uploads/input.txt")

        assert result.success
        assert "upload-data" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_command_rejects_host_paths_embedded_in_script_strings(self, sandbox):
        """Quoted scripts should still be inspected for host path access."""
        result = await sandbox.execute_command(
            'python -c "from pathlib import Path; print(Path(\'/etc/hosts\').read_text())"'
        )

        assert not result.success
        assert "outside sandbox" in result.stderr


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
        await provider.acquire("thread-789")
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

        thread_path = Path(temp_dir) / "thread-dirs" / "user-data"
        assert thread_path.exists()
        assert (thread_path / "workspace").exists()
        assert (thread_path / "uploads").exists()
        assert (thread_path / "outputs").exists()


class TestLocalSandboxSecurity:
    """Security tests for LocalSandbox."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def sandbox(self, temp_dir):
        """Create LocalSandbox instance."""
        thread_dir = Path(temp_dir) / "thread-sec"
        user_data_dir = thread_dir / "user-data"
        user_data_dir.mkdir(parents=True)
        path_mappings = {
            "/mnt/user-data/workspace": str(user_data_dir / "workspace"),
            "/mnt/user-data/uploads": str(user_data_dir / "uploads"),
            "/mnt/user-data/outputs": str(user_data_dir / "outputs"),
        }
        for mapped_path in path_mappings.values():
            Path(mapped_path).mkdir(parents=True, exist_ok=True)
        return LocalSandbox(id="thread-sec", path_mappings=path_mappings)

    @pytest.mark.asyncio
    async def test_reject_path_outside_sandbox(self, sandbox):
        """Should reject absolute paths outside sandbox."""
        with pytest.raises(SandboxSecurityError):
            await sandbox.read_file("/etc/passwd")

    @pytest.mark.asyncio
    async def test_reject_path_traversal(self, sandbox):
        """Should reject path traversal attempts."""
        with pytest.raises(SandboxSecurityError):
            await sandbox.read_file("/mnt/user-data/workspace/../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_reject_null_byte_in_path(self, sandbox):
        """Should reject paths with null bytes."""
        with pytest.raises(SandboxSecurityError):
            await sandbox.read_file("/mnt/user-data/workspace/test\x00.txt")

    @pytest.mark.asyncio
    async def test_reject_non_virtual_absolute_path(self, sandbox):
        """Should reject non-virtual absolute paths."""
        with pytest.raises(SandboxSecurityError):
            await sandbox.write_file("/tmp/malicious.txt", "content")

    @pytest.mark.asyncio
    async def test_allow_virtual_path(self, sandbox):
        """Should allow valid virtual paths."""
        # This should NOT raise an error
        await sandbox.write_file("/mnt/user-data/workspace/safe.txt", "content")
        content = await sandbox.read_file("/mnt/user-data/workspace/safe.txt")
        assert content == "content"

    @pytest.mark.asyncio
    async def test_list_dir_max_depth(self, sandbox):
        """Should respect max_depth parameter."""
        # Create nested directories
        await sandbox.write_file(
            "/mnt/user-data/workspace/level1/level2/level3/file.txt",
            "deep content",
        )

        # max_depth=0 should only list current directory
        entries = await sandbox.list_dir("/mnt/user-data/workspace", max_depth=0)
        names = [e.name for e in entries]
        assert "level1" in names
        assert "level2" not in names

        # max_depth=1 should include one level of subdirectories
        entries = await sandbox.list_dir("/mnt/user-data/workspace", max_depth=1)
        names = [e.name for e in entries]
        assert "level1" in names
        assert "level2" in names
        assert "level3" not in names


class TestLocalSandboxProviderCleanup:
    """Tests for LocalSandboxProvider cleanup functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_no_cleanup_by_default(self, temp_dir):
        """Should not cleanup by default on release."""
        provider = LocalSandboxProvider(base_dir=temp_dir, cleanup_on_release=False)
        sandbox = await provider.acquire("thread-cleanup-1")

        # Write a file
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "content")

        # Release sandbox
        await provider.release(sandbox)

        # Directory should still exist
        assert (Path(temp_dir) / "thread-cleanup-1").exists()

    @pytest.mark.asyncio
    async def test_cleanup_on_release_when_enabled(self, temp_dir):
        """Should cleanup when enabled on release."""
        provider = LocalSandboxProvider(base_dir=temp_dir, cleanup_on_release=True)
        sandbox = await provider.acquire("thread-cleanup-2")

        # Write a file
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "content")

        # Release sandbox
        await provider.release(sandbox)

        # Directory should be removed
        assert not (Path(temp_dir) / "thread-cleanup-2").exists()

    @pytest.mark.asyncio
    async def test_cleanup_override_on_release(self, temp_dir):
        """Should allow cleanup override on release."""
        provider = LocalSandboxProvider(base_dir=temp_dir, cleanup_on_release=False)
        sandbox = await provider.acquire("thread-cleanup-3")

        # Write a file
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "content")

        # Release with cleanup=True override
        await provider.release(sandbox, cleanup=True)

        # Directory should be removed despite default
        assert not (Path(temp_dir) / "thread-cleanup-3").exists()
