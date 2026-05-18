"""Redis cache for analytics queries.

5-minute TTL; key = analytics:{endpoint}:{range}:{granularity}.
Pass cache_bust=True to skip the cache for one read.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300


async def cached(
    *,
    cache_key: str,
    fetcher: Callable[[], Awaitable[dict[str, Any]]],
    cache_bust: bool = False,
) -> dict[str, Any]:
    from src.academic.cache.redis_client import redis_client

    if not redis_client.is_connected:
        try:
            await redis_client.connect()
        except Exception:
            logger.warning(
                "analytics cache: Redis not available, falling back to direct query"
            )
            return await fetcher()

    if not cache_bust:
        try:
            cached_value = await redis_client.client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)
        except Exception:
            logger.warning(
                "analytics cache read failed for %s", cache_key, exc_info=True
            )

    fresh = await fetcher()
    try:
        await redis_client.client.set(
            cache_key, json.dumps(fresh, default=str), ex=CACHE_TTL_SECONDS
        )
    except Exception:
        logger.warning(
            "analytics cache write failed for %s", cache_key, exc_info=True
        )
    return fresh
