"""Review target handler registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.dataservice.domains.review.contracts import ReviewItemProjection

ReviewApplyHandler = Callable[[ReviewItemProjection], Awaitable[dict[str, Any] | None]]


class ReviewHandlerRegistry:
    """In-memory registry for target-domain review apply handlers."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], ReviewApplyHandler] = {}

    def register(
        self,
        *,
        target_domain: str,
        target_kind: str,
        handler: ReviewApplyHandler,
    ) -> None:
        key = (target_domain, target_kind)
        self._handlers[key] = handler

    def get(
        self,
        *,
        target_domain: str,
        target_kind: str,
    ) -> ReviewApplyHandler | None:
        return self._handlers.get((target_domain, target_kind))

