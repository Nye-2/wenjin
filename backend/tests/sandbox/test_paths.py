# tests/sandbox/test_paths.py
"""Tests for virtual path mapping."""

from src.sandbox.paths import VirtualPathMapper


class TestVirtualPathMapper:
    def test_default_virtual_prefix(self):
        """Should use /mnt/user-data as default prefix."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        assert mapper.VIRTUAL_PREFIX == "/mnt/user-data"

    def test_to_physical_workspace(self):
        """Should map workspace path correctly."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        physical = mapper.to_physical(
            "/mnt/user-data/workspace/paper.tex",
            thread_id="thread-123",
        )
        assert physical == "/tmp/threads/thread-123/user-data/workspace/paper.tex"

    def test_to_physical_uploads(self):
        """Should map uploads path correctly."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        physical = mapper.to_physical(
            "/mnt/user-data/uploads/document.pdf",
            thread_id="thread-123",
        )
        assert physical == "/tmp/threads/thread-123/user-data/uploads/document.pdf"

    def test_to_physical_outputs(self):
        """Should map outputs path correctly."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        physical = mapper.to_physical(
            "/mnt/user-data/outputs/result.pdf",
            thread_id="thread-123",
        )
        assert physical == "/tmp/threads/thread-123/user-data/outputs/result.pdf"

    def test_to_physical_non_virtual_path(self):
        """Should return unchanged if not a virtual path."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        physical = mapper.to_physical(
            "/home/user/file.txt",
            thread_id="thread-123",
        )
        assert physical == "/home/user/file.txt"

    def test_to_virtual(self):
        """Should convert physical path back to virtual."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        virtual = mapper.to_virtual(
            "/tmp/threads/thread-123/user-data/workspace/paper.tex",
            thread_id="thread-123",
        )
        assert virtual == "/mnt/user-data/workspace/paper.tex"

    def test_translate_command(self):
        """Should translate virtual paths in commands."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        command = mapper.translate_command(
            "cat /mnt/user-data/workspace/file.txt",
            thread_id="thread-123",
        )
        assert command == "cat /tmp/threads/thread-123/user-data/workspace/file.txt"

    def test_translate_command_multiple_paths(self):
        """Should translate multiple virtual paths."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        command = mapper.translate_command(
            "cp /mnt/user-data/uploads/a.pdf /mnt/user-data/outputs/b.pdf",
            thread_id="thread-123",
        )
        assert "/tmp/threads/thread-123/user-data/uploads/a.pdf" in command
        assert "/tmp/threads/thread-123/user-data/outputs/b.pdf" in command

    def test_translate_command_no_virtual_paths(self):
        """Should return unchanged if no virtual paths."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        command = mapper.translate_command(
            "ls -la /home/user",
            thread_id="thread-123",
        )
        assert command == "ls -la /home/user"

    def test_get_thread_paths(self):
        """Should return all thread paths."""
        mapper = VirtualPathMapper(base_dir="/tmp/threads")
        paths = mapper.get_thread_paths(thread_id="thread-123")
        assert paths["workspace"] == "/tmp/threads/thread-123/user-data/workspace"
        assert paths["uploads"] == "/tmp/threads/thread-123/user-data/uploads"
        assert paths["outputs"] == "/tmp/threads/thread-123/user-data/outputs"
