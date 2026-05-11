"""Search source registry -- maps source names to instances."""

from __future__ import annotations

import logging
from typing import Any

from src.services.search.base import SearchSource

logger = logging.getLogger(__name__)

SEARCH_SOURCES: dict[str, type[SearchSource]] = {}


def register_search_source(name: str, cls: type[SearchSource]) -> None:
    SEARCH_SOURCES[name] = cls
    logger.debug("Registered search source: %s", name)


def get_search_source(name: str) -> SearchSource:
    cls = SEARCH_SOURCES.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown search source: {name}. Available: {sorted(SEARCH_SOURCES)}"
        )
    return cls()
