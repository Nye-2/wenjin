"""Tests for gateway event-loop watchdog."""

from __future__ import annotations

import pytest

from src.gateway.watchdog import WatchdogSample, run_event_loop_watchdog, update_consecutive_breaches


def test_update_consecutive_breaches_resets_on_healthy_sample():
    breached = WatchdogSample(lag_seconds=2.0, threshold_seconds=1.0)
    healthy = WatchdogSample(lag_seconds=0.1, threshold_seconds=1.0)

    consecutive = update_consecutive_breaches(0, sample=breached)
    assert consecutive == 1

    consecutive = update_consecutive_breaches(consecutive, sample=healthy)
    assert consecutive == 0


@pytest.mark.asyncio
async def test_run_event_loop_watchdog_triggers_callback_on_consecutive_breaches():
    timeline = iter([0.0, 1.2, 3.0, 5.1])
    triggered: list[tuple[float, int]] = []

    def _monotonic() -> float:
        return next(timeline)

    async def _sleep(_seconds: float) -> None:
        return None

    def _on_hard_block(sample: WatchdogSample, consecutive: int) -> None:
        triggered.append((sample.lag_seconds, consecutive))

    await run_event_loop_watchdog(
        interval_seconds=1.0,
        lag_threshold_seconds=0.5,
        max_consecutive_breaches=2,
        on_hard_block=_on_hard_block,
        monotonic=_monotonic,
        sleep_func=_sleep,
    )

    assert len(triggered) == 1
    lag_seconds, consecutive = triggered[0]
    assert lag_seconds > 0.5
    assert consecutive == 2

