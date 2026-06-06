"""Workspace sandbox file tools for the Wenjin-native harness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from src.sandbox.workspace_layout import (
    WORKSPACE_ROOT,
    is_workspace_protected_path,
    normalize_workspace_virtual_path,
)

from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .diff_tracker import build_file_change
from .output_budget import budget_text_output, select_lines

DEFAULT_READ_MAX_CHARS = 12_000
DEFAULT_SEARCH_MAX_MATCHES = 50


class HarnessPathError(ValueError):
    """Raised when a harness file path is outside policy."""


@dataclass(slots=True)
class SandboxFileTools:
    """File/search/write helpers scoped to one `/workspace` sandbox."""

    sandbox: Any
    context: HarnessRunContext
    policy: HarnessPolicy

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        max_chars: int | None = None,
    ) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="read")
        content = await self.sandbox.read_file(safe_path)
        selected = select_lines(content, start_line=start_line, end_line=end_line)
        budgeted = await budget_text_output(
            text=selected,
            tool_name="sandbox.read_file",
            context=self.context,
            sandbox=self.sandbox,
            output_budget=self.policy.output_budget,
            fallback_max_chars=max_chars or self._read_max_chars(),
        )
        return HarnessToolResult(
            preview_text=budgeted.preview_text,
            structured_payload={
                "path": safe_path,
                "start_line": start_line,
                "end_line": end_line,
                "bytes": len(content.encode("utf-8")),
                "selected_bytes": len(selected.encode("utf-8")),
            },
            output_refs=budgeted.output_refs,
            truncated=budgeted.truncated,
            externalized=budgeted.externalized,
        )

    async def list_dir(self, *, path: str = WORKSPACE_ROOT, max_depth: int = 1) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="read")
        entries = await self.sandbox.list_dir(safe_path, max_depth=max_depth)
        payload_entries = [
            {
                "name": entry.name,
                "path": _virtualize_path(entry.path),
                "is_dir": entry.is_dir,
                "size": entry.size,
            }
            for entry in entries
        ]
        lines = [
            f"{item['path']}{'/' if item['is_dir'] else ''}"
            for item in payload_entries[: self._max_matches()]
        ]
        return HarnessToolResult(
            preview_text="\n".join(lines),
            structured_payload={"path": safe_path, "entries": payload_entries},
            truncated=len(payload_entries) > self._max_matches(),
        )

    async def glob(self, *, pattern: str, max_matches: int | None = None) -> HarnessToolResult:
        safe_pattern = self._validate_glob_pattern(pattern)
        limit = max_matches or self._max_matches()
        matches = [
            _virtualize_path(str(path))
            for path in sorted(self._workspace_physical_root().glob(safe_pattern))
            if path.is_file()
        ][:limit]
        return HarnessToolResult(
            preview_text="\n".join(matches),
            structured_payload={"pattern": pattern, "matches": matches},
            truncated=len(matches) >= limit,
        )

    async def grep(
        self,
        *,
        pattern: str,
        glob: str = "**/*",
        max_matches: int | None = None,
    ) -> HarnessToolResult:
        safe_glob = self._validate_glob_pattern(glob)
        regex = re.compile(pattern)
        limit = max_matches or self._max_matches()
        matches: list[dict[str, Any]] = []
        for path in sorted(self._workspace_physical_root().glob(safe_glob)):
            if not path.is_file():
                continue
            virtual_path = _virtualize_path(str(path))
            if self._is_protected(virtual_path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(
                        {
                            "path": virtual_path,
                            "line": index,
                            "text": line[:500],
                        }
                    )
                    if len(matches) >= limit:
                        return self._grep_result(pattern, glob, matches, truncated=True)
        return self._grep_result(pattern, glob, matches, truncated=False)

    async def write_file(self, *, path: str, content: str) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="write")
        before = await self._read_existing(safe_path)
        await self.sandbox.write_file(safe_path, content)
        return HarnessToolResult(
            preview_text=f"Wrote {safe_path}",
            structured_payload={"path": safe_path, "bytes": len(content.encode("utf-8"))},
            file_change=build_file_change(
                path=safe_path,
                before=before,
                after=content,
                operation="add" if before is None else "update",
            ),
        )

    async def str_replace(self, *, path: str, old: str, new: str) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="write")
        before = await self.sandbox.read_file(safe_path)
        count = before.count(old)
        if count != 1:
            raise ValueError(f"str_replace expected exactly one match, found {count}")
        after = before.replace(old, new, 1)
        await self.sandbox.write_file(safe_path, after)
        return HarnessToolResult(
            preview_text=f"Updated {safe_path}",
            structured_payload={"path": safe_path, "replacement_count": 1},
            file_change=build_file_change(
                path=safe_path,
                before=before,
                after=after,
                operation="update",
            ),
        )

    def _validate_virtual_path(self, path: str, *, operation: str) -> str:
        try:
            normalized = normalize_workspace_virtual_path(path)
        except ValueError as exc:
            raise HarnessPathError(str(exc)) from exc
        if self._is_protected(normalized):
            raise HarnessPathError(f"protected path is not accessible: {normalized}")
        if operation == "write" and not self._can_write():
            raise PermissionError("harness policy does not allow filesystem writes")
        return normalized

    def _validate_glob_pattern(self, pattern: str) -> str:
        text = str(pattern or "").strip() or "**/*"
        if "\x00" in text or text.startswith("/") or ".." in PurePosixPath(text).parts:
            raise HarnessPathError("glob pattern must be workspace-relative")
        return text

    def _workspace_physical_root(self) -> Path:
        resolver = getattr(self.sandbox, "_resolve_path", None)
        if callable(resolver):
            return Path(resolver(WORKSPACE_ROOT))
        mappings = getattr(self.sandbox, "path_mappings", None)
        if isinstance(mappings, dict) and WORKSPACE_ROOT in mappings:
            return Path(mappings[WORKSPACE_ROOT])
        raise RuntimeError("sandbox does not expose a workspace root")

    def _is_protected(self, virtual_path: str) -> bool:
        return is_workspace_protected_path(
            virtual_path,
            protected_paths=tuple(self.policy.protected_paths),
        )

    def _read_max_chars(self) -> int:
        return int(self.policy.output_budget.get("read_max_chars") or DEFAULT_READ_MAX_CHARS)

    def _max_matches(self) -> int:
        return int(self.policy.output_budget.get("search_max_matches") or DEFAULT_SEARCH_MAX_MATCHES)

    def _can_write(self) -> bool:
        return "filesystem.write" in self.policy.permissions

    async def _read_existing(self, path: str) -> str | None:
        try:
            return await self.sandbox.read_file(path)
        except FileNotFoundError:
            return None

    @staticmethod
    def _grep_result(pattern: str, glob_pattern: str, matches: list[dict[str, Any]], *, truncated: bool) -> HarnessToolResult:
        preview = "\n".join(
            f"{item['path']}:{item['line']}: {item['text']}"
            for item in matches
        )
        return HarnessToolResult(
            preview_text=preview,
            structured_payload={"pattern": pattern, "glob": glob_pattern, "matches": matches},
            truncated=truncated,
        )


def _virtualize_path(path: str) -> str:
    marker = f"{WORKSPACE_ROOT}/"
    if marker in path:
        return f"{WORKSPACE_ROOT}/{path.split(marker, 1)[1]}"
    if path.endswith(WORKSPACE_ROOT):
        return WORKSPACE_ROOT
    return path
