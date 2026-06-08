"""Workspace sandbox file tools for the Wenjin-native harness."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from src.sandbox.workspace_layout import (
    WORKSPACE_ROOT,
    is_workspace_internal_path,
    is_workspace_protected_path,
    normalize_workspace_virtual_path,
)

from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .diff_tracker import build_file_change
from .output_budget import budget_text_output, select_lines

DEFAULT_READ_MAX_CHARS = 12_000
DEFAULT_DIFF_MAX_CHARS = 12_000
DEFAULT_SEARCH_MAX_MATCHES = 50
DEFAULT_GREP_MAX_FILE_BYTES = 1_000_000
DEFAULT_GREP_MAX_LINE_CHARS = 2_000
DEFAULT_GREP_BINARY_SAMPLE_BYTES = 8192


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
        self._require_read_permission()
        safe_path = self._validate_virtual_path(path, operation="read")
        self._require_workspace_physical_target(safe_path)
        self._require_tool_visible_physical_target(safe_path)
        content = await self.sandbox.read_file(safe_path)
        selected = select_lines(content, start_line=start_line, end_line=end_line)
        budgeted = await budget_text_output(
            text=selected,
            tool_name="sandbox.read_file",
            context=self.context,
            sandbox=self.sandbox,
            output_budget=self.policy.output_budget,
            fallback_max_chars=self._effective_read_max_chars(max_chars),
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
        self._require_read_permission()
        safe_path = self._validate_virtual_path(path, operation="read")
        entries = await self.sandbox.list_dir(safe_path, max_depth=max_depth)
        visible_entries = []
        for entry in entries:
            virtual_path = _virtualize_path(entry.path)
            if not self._is_tool_visible_path(virtual_path):
                continue
            if not self._is_tool_visible_entry(entry.path, virtual_path):
                continue
            visible_entries.append(
                {
                    "name": entry.name,
                    "path": virtual_path,
                    "is_dir": entry.is_dir,
                    "size": entry.size,
                }
            )
        limit = self._max_matches()
        payload_entries = visible_entries[:limit]
        lines = [
            f"{item['path']}{'/' if item['is_dir'] else ''}"
            for item in payload_entries
        ]
        return HarnessToolResult(
            preview_text="\n".join(lines),
            structured_payload={
                "path": safe_path,
                "entries": payload_entries,
                "total_entries": len(visible_entries),
                "returned_entries": len(payload_entries),
            },
            truncated=len(visible_entries) > limit,
        )

    async def glob(self, *, pattern: str, max_matches: int | None = None) -> HarnessToolResult:
        self._require_read_permission()
        safe_pattern = self._validate_glob_pattern(pattern)
        limit = self._effective_max_matches(max_matches)
        matches: list[str] = []
        truncated = False
        for path in sorted(self._workspace_physical_root().glob(safe_pattern)):
            if not self._is_workspace_physical_path(path):
                continue
            if not path.is_file():
                continue
            virtual_path = _virtualize_path(str(path))
            if not self._is_tool_visible_path(virtual_path):
                continue
            if not self._is_tool_visible_physical_target(path):
                continue
            if len(matches) >= limit:
                truncated = True
                break
            matches.append(virtual_path)
        return HarnessToolResult(
            preview_text="\n".join(matches),
            structured_payload={
                "pattern": pattern,
                "matches": matches,
                "returned_matches": len(matches),
                "match_limit": limit,
            },
            truncated=truncated,
        )

    async def grep(
        self,
        *,
        pattern: str,
        glob: str = "**/*",
        max_matches: int | None = None,
    ) -> HarnessToolResult:
        self._require_read_permission()
        safe_glob = self._validate_glob_pattern(glob)
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return _invalid_regex_result(pattern=pattern, glob_pattern=glob, error=exc)
        limit = self._effective_max_matches(max_matches)
        matches: list[dict[str, Any]] = []
        scanned_files = 0
        skipped_large_files = 0
        skipped_binary_files = 0
        skipped_long_lines = 0
        for path in sorted(self._workspace_physical_root().glob(safe_glob)):
            if not self._is_workspace_physical_path(path):
                continue
            if not path.is_file():
                continue
            virtual_path = _virtualize_path(str(path))
            if not self._is_tool_visible_path(virtual_path):
                continue
            if not self._is_tool_visible_physical_target(path):
                continue
            try:
                if self._grep_file_too_large(path):
                    skipped_large_files += 1
                    continue
                if self._is_binary_file(path):
                    skipped_binary_files += 1
                    continue
            except OSError:
                continue
            scanned_files += 1
            try:
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for index, line in enumerate(handle, start=1):
                        if len(line) > self._grep_max_line_chars():
                            skipped_long_lines += 1
                            continue
                        text = line.rstrip("\r\n")[:500]
                        if regex.search(line):
                            matches.append(
                                {
                                    "path": virtual_path,
                                    "line": index,
                                    "text": text,
                                }
                            )
                            if len(matches) >= limit:
                                return self._grep_result(
                                    pattern,
                                    glob,
                                    matches,
                                    match_limit=limit,
                                    truncated=True,
                                    scanned_files=scanned_files,
                                    skipped_large_files=skipped_large_files,
                                    skipped_binary_files=skipped_binary_files,
                                    skipped_long_lines=skipped_long_lines,
                                )
            except OSError:
                continue
        return self._grep_result(
            pattern,
            glob,
            matches,
            match_limit=limit,
            truncated=False,
            scanned_files=scanned_files,
            skipped_large_files=skipped_large_files,
            skipped_binary_files=skipped_binary_files,
            skipped_long_lines=skipped_long_lines,
        )

    async def write_file(self, *, path: str, content: str) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="write")
        self._require_workspace_physical_target(safe_path)
        self._require_tool_visible_physical_target(safe_path)
        before = await self._read_existing(safe_path)
        await self.sandbox.write_file(safe_path, content)
        file_change = await self._budget_file_change_diff(
            build_file_change(
                path=safe_path,
                before=before,
                after=content,
                operation="add" if before is None else "update",
            ),
            tool_name="sandbox.write_file",
        )
        return HarnessToolResult(
            preview_text=f"Wrote {safe_path}",
            structured_payload={"path": safe_path, "bytes": len(content.encode("utf-8"))},
            file_change=file_change,
        )

    async def str_replace(self, *, path: str, old: str, new: str) -> HarnessToolResult:
        safe_path = self._validate_virtual_path(path, operation="write")
        self._require_workspace_physical_target(safe_path)
        self._require_tool_visible_physical_target(safe_path)
        before = await self.sandbox.read_file(safe_path)
        count = before.count(old)
        if count != 1:
            raise ValueError(f"str_replace expected exactly one match, found {count}")
        after = before.replace(old, new, 1)
        await self.sandbox.write_file(safe_path, after)
        file_change = await self._budget_file_change_diff(
            build_file_change(
                path=safe_path,
                before=before,
                after=after,
                operation="update",
            ),
            tool_name="sandbox.str_replace",
        )
        return HarnessToolResult(
            preview_text=f"Updated {safe_path}",
            structured_payload={"path": safe_path, "replacement_count": 1},
            file_change=file_change,
        )

    def _validate_virtual_path(self, path: str, *, operation: str) -> str:
        text = str(path or "").strip()
        if text != WORKSPACE_ROOT and not text.startswith(f"{WORKSPACE_ROOT}/"):
            raise HarnessPathError(f"path must be under {WORKSPACE_ROOT}")
        try:
            normalized = normalize_workspace_virtual_path(text)
        except ValueError as exc:
            raise HarnessPathError(str(exc)) from exc
        if self._is_protected(normalized):
            raise HarnessPathError(f"protected path is not accessible: {normalized}")
        if is_workspace_internal_path(normalized):
            raise HarnessPathError(f"internal path is not accessible: {normalized}")
        if operation == "write":
            self._require_write_permissions()
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

    def _is_tool_visible_path(self, virtual_path: str) -> bool:
        return not self._is_protected(virtual_path) and not is_workspace_internal_path(virtual_path)

    def _is_tool_visible_entry(self, raw_path: str, virtual_path: str) -> bool:
        if virtual_path != WORKSPACE_ROOT and not virtual_path.startswith(f"{WORKSPACE_ROOT}/"):
            return False
        resolver = getattr(self.sandbox, "_resolve_path", None)
        if callable(resolver):
            try:
                physical_path = Path(resolver(virtual_path))
                return self._is_workspace_physical_path(physical_path) and self._is_tool_visible_physical_target(
                    physical_path
                )
            except Exception:  # noqa: BLE001 - provider-specific path safety failures are hidden from tools.
                return False
        physical_path = Path(raw_path)
        return self._is_workspace_physical_path(physical_path) and self._is_tool_visible_physical_target(physical_path)

    def _is_workspace_physical_path(self, path: Path) -> bool:
        try:
            resolved_path = str(path.resolve())
            resolved_root = str(self._workspace_physical_root().resolve())
            return os.path.commonpath([resolved_path, resolved_root]) == resolved_root
        except (OSError, RuntimeError, ValueError):
            return False

    def _require_workspace_physical_target(self, virtual_path: str) -> None:
        resolver = getattr(self.sandbox, "_resolve_path", None)
        if not callable(resolver):
            return
        try:
            physical_path = Path(resolver(virtual_path))
        except Exception as exc:  # noqa: BLE001 - provider-specific path safety failures are normalized here.
            raise HarnessPathError(f"path resolves outside workspace: {virtual_path}") from exc
        if not self._is_workspace_physical_path(physical_path):
            raise HarnessPathError(f"path resolves outside workspace: {virtual_path}")

    def _require_tool_visible_physical_target(self, virtual_path: str) -> None:
        resolver = getattr(self.sandbox, "_resolve_path", None)
        if not callable(resolver):
            return
        try:
            physical_path = Path(resolver(virtual_path))
        except Exception as exc:  # noqa: BLE001 - provider-specific path safety failures are normalized here.
            raise HarnessPathError(f"path resolves outside workspace: {virtual_path}") from exc
        target_virtual_path = self._workspace_target_virtual_path(physical_path)
        if target_virtual_path is None:
            raise HarnessPathError(f"path resolves outside workspace: {virtual_path}")
        if self._is_protected(target_virtual_path):
            raise HarnessPathError(f"protected target is not accessible: {virtual_path}")
        if is_workspace_internal_path(target_virtual_path):
            raise HarnessPathError(f"internal target is not accessible: {virtual_path}")

    def _is_tool_visible_physical_target(self, path: Path) -> bool:
        target_virtual_path = self._workspace_target_virtual_path(path)
        if target_virtual_path is None:
            return False
        return self._is_tool_visible_path(target_virtual_path)

    def _workspace_target_virtual_path(self, path: Path) -> str | None:
        try:
            resolved_path = path.resolve()
            resolved_root = self._workspace_physical_root().resolve()
            relative = resolved_path.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError):
            return None
        if not relative.parts:
            return WORKSPACE_ROOT
        return f"{WORKSPACE_ROOT}/{relative.as_posix()}"

    def _read_max_chars(self) -> int:
        return int(self.policy.output_budget.get("read_max_chars") or DEFAULT_READ_MAX_CHARS)

    def _diff_max_chars(self) -> int:
        return int(self.policy.output_budget.get("diff_max_chars") or DEFAULT_DIFF_MAX_CHARS)

    def _diff_output_budget(self) -> dict[str, Any]:
        budget = dict(self.policy.output_budget or {})
        remaps = {
            "diff_externalize_above_chars": "externalize_above_chars",
            "diff_preview_head_chars": "preview_head_chars",
            "diff_preview_tail_chars": "preview_tail_chars",
        }
        for source, target in remaps.items():
            if source in budget:
                budget[target] = budget[source]
        return budget

    def _max_matches(self) -> int:
        return int(self.policy.output_budget.get("search_max_matches") or DEFAULT_SEARCH_MAX_MATCHES)

    def _grep_max_file_bytes(self) -> int:
        return int(self.policy.output_budget.get("grep_max_file_bytes") or DEFAULT_GREP_MAX_FILE_BYTES)

    def _grep_max_line_chars(self) -> int:
        return int(self.policy.output_budget.get("grep_max_line_chars") or DEFAULT_GREP_MAX_LINE_CHARS)

    def _effective_read_max_chars(self, requested: int | None) -> int:
        policy_limit = self._read_max_chars()
        if requested is None or requested <= 0:
            return policy_limit
        return min(requested, policy_limit)

    def _effective_max_matches(self, requested: int | None) -> int:
        policy_limit = self._max_matches()
        if requested is None or requested <= 0:
            return policy_limit
        return min(requested, policy_limit)

    def _can_write(self) -> bool:
        return "filesystem.write" in self.policy.permissions

    def _can_diff(self) -> bool:
        return "filesystem.diff" in self.policy.permissions

    def _require_read_permission(self) -> None:
        if "filesystem.read" not in self.policy.permissions:
            raise PermissionError("harness policy does not allow filesystem reads")

    def _require_write_permissions(self) -> None:
        if not self._can_write():
            raise PermissionError("harness policy does not allow filesystem writes")
        if not self._can_diff():
            raise PermissionError("harness policy does not allow filesystem diff tracking")

    def _grep_file_too_large(self, path: Path) -> bool:
        max_bytes = self._grep_max_file_bytes()
        return max_bytes > 0 and path.stat().st_size > max_bytes

    @staticmethod
    def _is_binary_file(path: Path) -> bool:
        with path.open("rb") as handle:
            return b"\0" in handle.read(DEFAULT_GREP_BINARY_SAMPLE_BYTES)

    async def _read_existing(self, path: str) -> str | None:
        try:
            return await self.sandbox.read_file(path)
        except FileNotFoundError:
            return None

    async def _budget_file_change_diff(self, change: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
        diff = str(change.get("unified_diff") or "")
        budgeted = await budget_text_output(
            text=diff,
            tool_name=f"{tool_name}.diff",
            context=self.context,
            sandbox=self.sandbox,
            output_budget=self._diff_output_budget(),
            fallback_max_chars=self._diff_max_chars(),
            extension="diff",
        )
        if not budgeted.truncated and not budgeted.externalized:
            return change

        bounded = dict(change)
        bounded["unified_diff"] = budgeted.preview_text
        bounded["diff_truncated"] = budgeted.truncated
        bounded["diff_externalized"] = budgeted.externalized
        if budgeted.output_refs:
            bounded["diff_output_refs"] = list(budgeted.output_refs)
        return bounded

    @staticmethod
    def _grep_result(
        pattern: str,
        glob_pattern: str,
        matches: list[dict[str, Any]],
        *,
        match_limit: int,
        truncated: bool,
        scanned_files: int,
        skipped_large_files: int,
        skipped_binary_files: int,
        skipped_long_lines: int,
    ) -> HarnessToolResult:
        preview = "\n".join(
            f"{item['path']}:{item['line']}: {item['text']}"
            for item in matches
        )
        return HarnessToolResult(
            preview_text=preview,
            structured_payload={
                "pattern": pattern,
                "glob": glob_pattern,
                "matches": matches,
                "returned_matches": len(matches),
                "match_limit": match_limit,
                "scanned_files": scanned_files,
                "skipped_large_files": skipped_large_files,
                "skipped_binary_files": skipped_binary_files,
                "skipped_long_lines": skipped_long_lines,
            },
            truncated=truncated,
        )


def _invalid_regex_result(*, pattern: str, glob_pattern: str, error: re.error) -> HarnessToolResult:
    error_text = str(error).strip() or type(error).__name__
    return HarnessToolResult(
        preview_text=f"invalid regular expression for sandbox.grep: {error_text}",
        structured_payload={
            "pattern": pattern,
            "glob": glob_pattern,
            "matches": [],
            "returned_matches": 0,
            "match_limit": 0,
            "scanned_files": 0,
            "skipped_large_files": 0,
            "skipped_binary_files": 0,
            "skipped_long_lines": 0,
            "error_code": "invalid_regex",
            "error": error_text,
        },
        error=f"invalid_regex: {error_text}",
    )


def _virtualize_path(path: str) -> str:
    marker = f"{WORKSPACE_ROOT}/"
    if marker in path:
        return f"{WORKSPACE_ROOT}/{path.split(marker, 1)[1]}"
    if path.endswith(WORKSPACE_ROOT):
        return WORKSPACE_ROOT
    return path
