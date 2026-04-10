"""Helpers for validating runtime middleware configuration."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig


def require_thread_id(config: RunnableConfig | None, *, component: str) -> str:
    """Return the configured thread ID or raise when it is missing."""
    runtime_config = config or {}
    configurable = runtime_config.get("configurable", {})
    thread_id = str(configurable.get("thread_id") or "").strip()
    if not thread_id:
        raise RuntimeError(f"{component} requires config.configurable.thread_id.")
    return thread_id
