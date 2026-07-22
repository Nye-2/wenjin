"""Redis-backed global capacity fencing for Mission subagent quanta."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from src.observability.prometheus import track_mission_subagent_capacity
from src.subagent_runtime.contracts import SubagentJobSpec

logger = logging.getLogger(__name__)

_ACQUIRE_LUA = """
local time = redis.call('TIME')
local now_ms = (tonumber(time[1]) * 1000) + math.floor(tonumber(time[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    return 0
end
local expires_ms = now_ms + tonumber(ARGV[2])
redis.call('ZADD', KEYS[1], expires_ms, ARGV[3])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

_RELEASE_LUA = """
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


class RedisConnectionPort(Protocol):
    @property
    def client(self) -> Any: ...


class RedisSubagentCapacityLimiter:
    """Lease one of a bounded number of slots across all worker replicas."""

    def __init__(
        self,
        redis: RedisConnectionPort,
        *,
        limit: int = 4,
        lease_ttl_seconds: int = 240,
        key: str = "runtime:mission:capacity:subagent",
    ) -> None:
        if limit < 1 or lease_ttl_seconds < 1:
            raise ValueError("subagent capacity and lease TTL must be positive")
        self.redis = redis
        self.limit = limit
        self.lease_ttl_ms = lease_ttl_seconds * 1000
        self.key = key

    async def try_acquire(self, job: SubagentJobSpec) -> str | None:
        token = f"{job.job_id}:{uuid.uuid4().hex}"
        try:
            acquired = await self.redis.client.eval(
                _ACQUIRE_LUA,
                1,
                self.key,
                self.limit,
                self.lease_ttl_ms,
                token,
            )
        except Exception:
            track_mission_subagent_capacity("unavailable")
            logger.warning(
                "Global subagent capacity is unavailable; quantum deferred",
                exc_info=True,
            )
            return None
        if int(acquired or 0) == 1:
            track_mission_subagent_capacity("acquired")
            return token
        track_mission_subagent_capacity("saturated")
        return None

    async def release(self, token: str) -> None:
        try:
            await self.redis.client.eval(
                _RELEASE_LUA,
                1,
                self.key,
                token,
            )
        except Exception:
            track_mission_subagent_capacity("release_failed")
            # The lease is self-expiring. A release outage may reduce capacity
            # temporarily, but must not turn a completed receipt into failure.
            logger.warning(
                "Global subagent capacity release failed; lease will expire",
                exc_info=True,
            )
        else:
            track_mission_subagent_capacity("released")


__all__ = ["RedisSubagentCapacityLimiter"]
