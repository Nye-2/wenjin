"""Virtual path mapping for sandbox isolation."""

import re
from pathlib import Path
from typing import Any


class VirtualPathMapper:
    """Maps virtual paths to physical paths for sandbox isolation.

    Virtual paths (seen by agent):
        /mnt/user-data/workspace/...
        /mnt/user-data/uploads/...
        /mnt/user-data/outputs/...

    Physical paths (actual filesystem):
        {base_dir}/{thread_id}/user-data/workspace/...
        {base_dir}/{thread_id}/user-data/uploads/...
        {base_dir}/{thread_id}/user-data/outputs/...
    """

    VIRTUAL_PREFIX = "/mnt/user-data"
    SUBDIRS = ["workspace", "uploads", "outputs"]

    def __init__(self, base_dir: str):
        """Initialize path mapper."""
        self.base_dir = str(Path(base_dir).resolve())

    def get_thread_paths(self, thread_id: str) -> dict[str, str]:
        """Get all thread-specific paths."""
        thread_base = Path(self.base_dir) / thread_id / "user-data"
        return {
            subdir: str(thread_base / subdir)
            for subdir in self.SUBDIRS
        }

    def to_physical(self, virtual_path: str, thread_id: str) -> str:
        """Convert virtual path to physical path."""
        if not virtual_path.startswith(self.VIRTUAL_PREFIX):
            return virtual_path

        relative = virtual_path[len(self.VIRTUAL_PREFIX):].lstrip("/")
        if not relative:
            return str(Path(self.base_dir) / thread_id / "user-data")

        parts = relative.split("/", 1)
        subdir = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        if subdir not in self.SUBDIRS:
            return str(Path(self.base_dir) / thread_id / relative)

        thread_paths = self.get_thread_paths(thread_id)
        base = thread_paths[subdir]

        if rest:
            return str(Path(base) / rest)
        return base

    def to_virtual(self, physical_path: str, thread_id: str) -> str:
        """Convert physical path to virtual path."""
        resolved = str(Path(physical_path).resolve())
        thread_paths = self.get_thread_paths(thread_id)

        for subdir in reversed(self.SUBDIRS):
            base = thread_paths[subdir]
            base_resolved = str(Path(base).resolve())

            if resolved.startswith(base_resolved):
                relative = resolved[len(base_resolved):].lstrip("/")
                if relative:
                    return f"{self.VIRTUAL_PREFIX}/{subdir}/{relative}"
                return f"{self.VIRTUAL_PREFIX}/{subdir}"

        return physical_path

    def translate_command(self, command: str, thread_id: str) -> str:
        """Translate all virtual paths in a command string."""
        if self.VIRTUAL_PREFIX not in command:
            return command

        pattern = re.compile(
            rf"{re.escape(self.VIRTUAL_PREFIX)}(/[^\s\"';&|<>()]*)?"
        )

        def replace_match(match: re.Match) -> str:
            virtual_path = match.group(0)
            return self.to_physical(virtual_path, thread_id)

        return pattern.sub(replace_match, command)
