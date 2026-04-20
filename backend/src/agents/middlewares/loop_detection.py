"""Loop detection middleware to break repetitive tool-call loops."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict, defaultdict
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

_DEFAULT_WARN_THRESHOLD = 3
_DEFAULT_HARD_LIMIT = 5
_DEFAULT_WINDOW_SIZE = 20
_DEFAULT_MAX_TRACKED_THREADS = 100
_DEFAULT_TOOL_FREQ_WARN = 30
_DEFAULT_TOOL_FREQ_HARD_LIMIT = 50

_WARNING_MSG = (
    "[LOOP DETECTED] 你正在重复调用相同工具。"
    "请停止继续调用工具并直接给出最终结论；如无法完成，请总结已完成内容与缺失信息。"
)
_TOOL_FREQ_WARNING_MSG = (
    "[LOOP DETECTED] 工具 {tool_name} 已调用 {count} 次。"
    "请停止继续调用工具并直接给出最终结论；如无法完成，请总结已完成内容与缺失信息。"
)
_HARD_STOP_MSG = (
    "[FORCED STOP] 重复工具调用超过安全阈值，"
    "将停止继续调用工具并基于已有结果给出最终结论。"
)
_TOOL_FREQ_HARD_STOP_MSG = (
    "[FORCED STOP] 工具 {tool_name} 已调用 {count} 次，"
    "超过安全阈值。将停止继续调用工具并基于已有结果给出最终结论。"
)


def _normalize_tool_call_args(raw_args: object) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw_args, dict):
        return raw_args, None

    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, raw_args
        if isinstance(parsed, dict):
            return parsed, None
        return {}, json.dumps(parsed, sort_keys=True, ensure_ascii=False, default=str)

    if raw_args is None:
        return {}, None

    return {}, json.dumps(raw_args, sort_keys=True, ensure_ascii=False, default=str)


def _stable_tool_key(name: str, args: dict[str, Any], fallback_key: str | None) -> str:
    if name == "read_file" and fallback_key is None:
        file_path = str(args.get("file_path") or args.get("path") or "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        bucket_size = 200
        try:
            start = int(start_line) if start_line is not None else 1
        except (TypeError, ValueError):
            start = 1
        try:
            end = int(end_line) if end_line is not None else start
        except (TypeError, ValueError):
            end = start
        start, end = sorted((max(start, 1), max(end, 1)))
        start_bucket = (start - 1) // bucket_size
        end_bucket = (end - 1) // bucket_size
        return f"{file_path}:{start_bucket}-{end_bucket}"

    if name in {"write_file", "str_replace"}:
        if fallback_key is not None:
            return fallback_key
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)

    salient_fields = ("path", "file_path", "url", "query", "command", "pattern", "glob", "cmd")
    stable_args = {field: args[field] for field in salient_fields if args.get(field) is not None}
    if stable_args:
        return json.dumps(stable_args, sort_keys=True, ensure_ascii=False, default=str)

    if fallback_key is not None:
        return fallback_key
    return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def _hash_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    normalized: list[str] = []
    for tool_call in tool_calls:
        name = str(tool_call.get("name") or "")
        args, fallback_key = _normalize_tool_call_args(tool_call.get("args"))
        key = _stable_tool_key(name, args, fallback_key)
        normalized.append(f"{name}:{key}")
    normalized.sort()
    blob = json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:12]


class LoopDetectionMiddleware(Middleware):
    """Detect repeated tool-call patterns and force graceful stop."""

    def __init__(
        self,
        warn_threshold: int = _DEFAULT_WARN_THRESHOLD,
        hard_limit: int = _DEFAULT_HARD_LIMIT,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        max_tracked_threads: int = _DEFAULT_MAX_TRACKED_THREADS,
        tool_freq_warn: int = _DEFAULT_TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _DEFAULT_TOOL_FREQ_HARD_LIMIT,
    ) -> None:
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.max_tracked_threads = max_tracked_threads
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit

        self._lock = threading.Lock()
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)
        self._tool_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)

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
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return {}

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if not tool_calls:
            return {}

        warning_msg, should_hard_stop = self._track_and_check(
            tool_calls=tool_calls,
            thread_id=self._resolve_thread_id(config),
        )
        if warning_msg is None:
            return {}

        updated = self._clone_ai_message(last_msg)
        updated.content = self._append_text(updated.content, warning_msg)
        if should_hard_stop:
            updated.tool_calls = []

        return {"messages": [*messages[:-1], updated]}

    @staticmethod
    def _resolve_thread_id(config: RunnableConfig | None) -> str:
        runtime_config = config or {}
        configurable = runtime_config.get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "").strip()
        return thread_id or "default"

    @staticmethod
    def _append_text(content: str | list[Any] | None, text: str) -> str | list[Any]:
        if content is None:
            return text
        if isinstance(content, str):
            suffix = "\n\n" if content else ""
            return f"{content}{suffix}{text}"
        if isinstance(content, list):
            return [*content, {"type": "text", "text": text}]
        return f"{content}\n\n{text}"

    @staticmethod
    def _clone_ai_message(message: AIMessage) -> AIMessage:
        if hasattr(message, "model_copy"):
            return message.model_copy(deep=True)
        return deepcopy(message)

    def _evict_if_needed(self) -> None:
        while len(self._history) > self.max_tracked_threads:
            evicted, _ = self._history.popitem(last=False)
            self._warned.pop(evicted, None)
            self._tool_freq.pop(evicted, None)
            self._tool_freq_warned.pop(evicted, None)

    def _track_and_check(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        thread_id: str,
    ) -> tuple[str | None, bool]:
        call_hash = _hash_tool_calls(tool_calls)

        with self._lock:
            if thread_id in self._history:
                self._history.move_to_end(thread_id)
            else:
                self._history[thread_id] = []
                self._evict_if_needed()

            history = self._history[thread_id]
            history.append(call_hash)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size :]

            count = history.count(call_hash)

            if count >= self.hard_limit:
                logger.warning(
                    "LoopDetection hard limit reached: thread=%s hash=%s count=%s",
                    thread_id,
                    call_hash,
                    count,
                )
                return _HARD_STOP_MSG, True

            if count >= self.warn_threshold:
                warned_hashes = self._warned[thread_id]
                if call_hash not in warned_hashes:
                    warned_hashes.add(call_hash)
                    return _WARNING_MSG, False

            freq = self._tool_freq[thread_id]
            warned_tools = self._tool_freq_warned[thread_id]
            for tool_call in tool_calls:
                name = str(tool_call.get("name") or "")
                if not name:
                    continue
                freq[name] += 1
                tool_count = freq[name]

                if tool_count >= self.tool_freq_hard_limit:
                    return _TOOL_FREQ_HARD_STOP_MSG.format(tool_name=name, count=tool_count), True

                if tool_count >= self.tool_freq_warn and name not in warned_tools:
                    warned_tools.add(name)
                    return _TOOL_FREQ_WARNING_MSG.format(tool_name=name, count=tool_count), False

        return None, False
