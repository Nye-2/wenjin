"""Sandbox command auditing middleware for bash tool calls."""

from __future__ import annotations

import json
import logging
import re
import shlex
import threading
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

_HIGH_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\*?|/home\b|/root\b)\s*$"),
    re.compile(r"dd\s+if="),
    re.compile(r"mkfs"),
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r">+\s*/etc/"),
    re.compile(r"\|\s*(ba)?sh\b"),
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    re.compile(r"base64\s+.*-d.*\|"),
    re.compile(r">+\s*(/usr/bin/|/bin/|/sbin/)"),
    re.compile(r">+\s*~/?\.(bashrc|profile|zshrc|bash_profile)"),
    re.compile(r"/proc/[^/]+/environ"),
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    re.compile(r"/dev/tcp/"),
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),
    re.compile(r"while\s+true.*&\s*done"),
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chmod\s+777"),
    re.compile(r"pip3?\s+install"),
    re.compile(r"apt(-get)?\s+install"),
    re.compile(r"\b(sudo|su)\b"),
    re.compile(r"\bPATH\s*="),
]


def _split_compound_command(command: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    escaping = False
    index = 0

    while index < len(command):
        char = command[index]
        if escaping:
            current.append(char)
            escaping = False
            index += 1
            continue

        if char == "\\" and not in_single_quote:
            current.append(char)
            escaping = True
            index += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            index += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            index += 1
            continue

        if not in_single_quote and not in_double_quote:
            if command.startswith("&&", index) or command.startswith("||", index):
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 2
                continue
            if char == ";":
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 1
                continue

        current.append(char)
        index += 1

    if in_single_quote or in_double_quote or escaping:
        return [command]

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts if parts else [command]


def _classify_single_command(command: str) -> str:
    normalized = " ".join(command.split())

    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    try:
        tokens = shlex.split(command)
        joined = " ".join(tokens)
        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(joined):
                return "block"
    except ValueError:
        return "block"

    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(normalized):
            return "warn"

    return "pass"


def _classify_command(command: str) -> str:
    normalized = " ".join(command.split())
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    verdict = "pass"
    for sub_command in _split_compound_command(command):
        current = _classify_single_command(sub_command)
        if current == "block":
            return "block"
        if current == "warn":
            verdict = "warn"
    return verdict


class SandboxAuditMiddleware(Middleware):
    """Audit bash command safety and block dangerous invocations."""

    _AUDIT_COMMAND_LIMIT = 200

    def __init__(self) -> None:
        self._warned_calls: dict[str, str] = {}
        self._lock = threading.Lock()

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        return {}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        return {}

    async def before_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if tool_name != "bash":
            return tool_name, tool_args

        command = str(tool_args.get("command") or "")
        verdict = _classify_command(command)
        thread_id = self._resolve_thread_id(config)
        self._write_audit(thread_id=thread_id, command=command, verdict=verdict, truncate=True)

        call_id = self._resolve_tool_call_id(config)
        if verdict == "block":
            raise RuntimeError(
                "Command blocked by sandbox audit: detected high-risk shell pattern."
            )

        if verdict == "warn" and call_id:
            with self._lock:
                self._warned_calls[call_id] = command

        return tool_name, tool_args

    async def after_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_result: Any,
    ) -> Any:
        if tool_name != "bash":
            return tool_result

        call_id = self._resolve_tool_call_id(config)
        if not call_id:
            return tool_result

        with self._lock:
            warned_command = self._warned_calls.pop(call_id, None)

        if not warned_command:
            return tool_result

        warning_text = (
            f"\n\n[Sandbox Audit Warning] `{warned_command}` 被判定为中风险命令，"
            "请确认该操作不会破坏运行环境。"
        )
        return self._append_warning(tool_result, warning_text)

    @staticmethod
    def _resolve_thread_id(config: RunnableConfig | None) -> str:
        runtime_config = config or {}
        configurable = runtime_config.get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "").strip()
        return thread_id or "unknown"

    @staticmethod
    def _resolve_tool_call_id(config: RunnableConfig | None) -> str | None:
        runtime_config = config or {}
        configurable = runtime_config.get("configurable", {})
        tool_call_id = str(configurable.get("tool_call_id") or "").strip()
        return tool_call_id or None

    @staticmethod
    def _append_warning(tool_result: Any, warning_text: str) -> Any:
        if isinstance(tool_result, ToolMessage):
            if isinstance(tool_result.content, list):
                tool_result.content = [*tool_result.content, {"type": "text", "text": warning_text}]
            else:
                tool_result.content = f"{tool_result.content}{warning_text}"
            return tool_result
        if isinstance(tool_result, str):
            return f"{tool_result}{warning_text}"
        return tool_result

    def _write_audit(
        self,
        *,
        thread_id: str,
        command: str,
        verdict: str,
        truncate: bool = False,
    ) -> None:
        audited_command = command
        if truncate and len(command) > self._AUDIT_COMMAND_LIMIT:
            audited_command = f"{command[: self._AUDIT_COMMAND_LIMIT]}... ({len(command)} chars)"
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "thread_id": thread_id,
            "command": audited_command,
            "verdict": verdict,
        }
        logger.info("[SandboxAudit] %s", json.dumps(record, ensure_ascii=False))
