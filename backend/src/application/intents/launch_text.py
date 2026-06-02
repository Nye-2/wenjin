"""Text normalization helpers for feature launch/resume orchestration."""

from __future__ import annotations

import re
from typing import Any

_GENERIC_LAUNCH_MESSAGES = {
    "开始",
    "开始吧",
    "确认",
    "确认启动",
    "继续",
    "继续吧",
}
_GENERIC_LAUNCH_MESSAGES_EN = {
    "start",
    "start now",
    "go ahead",
    "continue",
    "run",
    "confirm",
}
_GENERIC_FEATURE_ENTRY_PATTERN = re.compile(r"^请帮我开始「.+」。?$")
_WORKBENCH_LAUNCH_PREFIX = "请启动「"
_WORKBENCH_CONTEXT_GUARD = "如果当前对话缺少具体研究主题、材料或目标"
_WORKBENCH_EXECUTION_GUARD = "请先判断是否需要实验或检索"


def normalize_inline_text(value: Any) -> str:
    """Collapse arbitrary text-like values to single-line normalized text."""
    return " ".join(str(value or "").strip().split())


def is_generic_feature_launch_text(value: Any) -> bool:
    """Return whether text is a generic launch/continue phrase."""
    normalized = normalize_inline_text(value)
    if not normalized:
        return True
    if (
        normalized.startswith(_WORKBENCH_LAUNCH_PREFIX)
        and _WORKBENCH_CONTEXT_GUARD in normalized
        and _WORKBENCH_EXECUTION_GUARD in normalized
    ):
        return True
    if _GENERIC_FEATURE_ENTRY_PATTERN.match(normalized):
        return True
    if normalized in _GENERIC_LAUNCH_MESSAGES:
        return True
    return normalized.lower() in _GENERIC_LAUNCH_MESSAGES_EN
