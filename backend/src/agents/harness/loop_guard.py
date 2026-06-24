"""Repeated-call guard for harness tool loops."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .contracts import HarnessStopReason


@dataclass(frozen=True, slots=True)
class LoopGuardDecision:
    """Decision returned after recording one tool call fingerprint."""

    allowed: bool
    count: int
    should_warn: bool = False
    stop_reason: HarnessStopReason | None = None


@dataclass(slots=True)
class HarnessLoopGuard:
    """Detect repeated identical calls and total tool budget exhaustion."""

    warn_threshold: int = 3
    repeated_hard_limit: int = 5
    total_hard_limit: int = 30
    _counts: dict[str, int] | None = None
    _total_count: int = 0

    def record(self, tool_name: str, args: dict[str, Any]) -> LoopGuardDecision:
        if self._counts is None:
            self._counts = {}
        self._total_count += 1
        if self._total_count >= self.total_hard_limit:
            return LoopGuardDecision(
                allowed=False,
                count=self._total_count,
                should_warn=True,
                stop_reason="tool_total_hard_stop",
            )
        key = _fingerprint(tool_name, args)
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if count >= self.repeated_hard_limit:
            return LoopGuardDecision(
                allowed=False,
                count=count,
                should_warn=True,
                stop_reason="tool_loop_hard_stop",
            )
        return LoopGuardDecision(
            allowed=True,
            count=count,
            should_warn=count >= self.warn_threshold,
        )


def _fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": args},
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
