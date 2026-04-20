"""Gateway event-loop watchdog for stuck-loop self-healing."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchdogSample:
    """One event-loop lag sample."""

    lag_seconds: float
    threshold_seconds: float

    @property
    def breached(self) -> bool:
        return self.lag_seconds > self.threshold_seconds


def update_consecutive_breaches(
    current: int,
    *,
    sample: WatchdogSample,
) -> int:
    """Update consecutive breach count based on latest sample."""
    if sample.breached:
        return current + 1
    return 0


async def run_event_loop_watchdog(
    *,
    interval_seconds: float,
    lag_threshold_seconds: float,
    max_consecutive_breaches: int,
    on_hard_block: Callable[[WatchdogSample, int], None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Continuously detect severe event-loop lag and trigger a hard action."""
    expected_wakeup = monotonic() + interval_seconds
    consecutive_breaches = 0

    while True:
        await sleep_func(interval_seconds)
        now = monotonic()
        lag_seconds = max(0.0, now - expected_wakeup)
        expected_wakeup = now + interval_seconds

        sample = WatchdogSample(
            lag_seconds=lag_seconds,
            threshold_seconds=lag_threshold_seconds,
        )
        consecutive_breaches = update_consecutive_breaches(
            consecutive_breaches,
            sample=sample,
        )
        if not sample.breached:
            continue

        logger.error(
            "Gateway event loop lag detected: lag=%.3fs threshold=%.3fs consecutive=%s/%s",
            sample.lag_seconds,
            sample.threshold_seconds,
            consecutive_breaches,
            max_consecutive_breaches,
        )
        if consecutive_breaches < max_consecutive_breaches:
            continue

        if on_hard_block is not None:
            on_hard_block(sample, consecutive_breaches)
            return

        logger.critical(
            "Gateway event loop appears blocked; forcing process exit for container restart"
        )
        os._exit(1)
