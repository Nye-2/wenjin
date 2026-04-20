"""Shared model routing helpers for subagent execution paths."""

from __future__ import annotations

from src.models.router import route_model


def route_subagent_model(
    *,
    requested_model: str | None = None,
    thread_model: str | None = None,
) -> str | None:
    """Route a subagent model id from configured model pools.

    Returns a routed model id when possible. If routing fails (for example in a
    partially mocked test environment), falls back to the first non-empty input.
    """
    try:
        return route_model(
            requested_model=requested_model,
            thread_model=thread_model,
            preferred_categories=("tool", "gen"),
            allowed_categories=("tool", "gen"),
            require_tools=True,
        )
    except Exception:
        for candidate in (requested_model, thread_model):
            normalized = str(candidate or "").strip()
            if normalized:
                return normalized
    return None
