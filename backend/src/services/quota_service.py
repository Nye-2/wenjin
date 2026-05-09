"""Quota service — Redis-backed rate limiting and resource tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class QuotaExceeded(Exception):
    """Raised when a user's quota for a given resource kind is exceeded."""


@dataclass
class QuotaUsage:
    """Snapshot of a user's current quota consumption."""

    tokens_daily: int = 0
    executions_concurrent: int = 0
    storage_bytes: int = 0


# Atomic check-and-increment Lua script.
# Returns the new counter value on success, or -1 if limit would be exceeded.
LUA_CONSUME = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
if current + amount <= limit then
    local new_val = redis.call('INCRBY', KEYS[1], amount)
    if ARGV[3] ~= '0' then
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    end
    return new_val
else
    return -1
end
"""


class QuotaService:
    """Tracks and enforces per-user resource quotas via Redis.

    Supported kinds: ``tokens_daily``, ``executions_concurrent``, ``storage_bytes``.
    """

    def __init__(
        self,
        redis,
        *,
        daily_token_limit: int = 1_000_000,
        concurrent_exec_limit: int = 1,
        storage_limit_bytes: int = 5 * 1024**3,
    ) -> None:
        self.redis = redis
        self.limits: dict[str, int] = {
            "tokens_daily": daily_token_limit,
            "executions_concurrent": concurrent_exec_limit,
            "storage_bytes": storage_limit_bytes,
        }

    def _key(self, user_id: str, kind: str) -> str:
        if kind == "tokens_daily":
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            return f"quota:{user_id}:{kind}:{day}"
        return f"quota:{user_id}:{kind}"

    async def check(self, user_id: str, *, kind: str, amount: int = 0) -> bool:
        """Read-only inspection: return True if the user can consume *amount* more of *kind*.

        This is informational only and does not gate the actual consume — use
        consume() for the authoritative atomic check-and-increment.
        """
        key = self._key(user_id, kind)
        current = await self.redis.get(key)
        used = int(current) if current else 0
        return (used + amount) <= self.limits[kind]

    async def consume(self, user_id: str, *, kind: str, amount: int) -> int:
        """Atomically check and increment usage by *amount*.

        Uses a Lua script so the check-and-increment is a single Redis
        operation, eliminating the TOCTOU race in a plain incrby/post-check
        approach.

        Returns:
            The new counter value after incrementing.

        Raises:
            QuotaExceeded: If current + amount would exceed the limit.
        """
        key = self._key(user_id, kind)
        limit = self.limits[kind]
        # For tokens_daily, set a 48-hour TTL so keys auto-expire.
        ttl_seconds = 172800 if kind == "tokens_daily" else 0
        result = await self.redis.eval(LUA_CONSUME, 1, key, limit, amount, ttl_seconds)
        if result == -1:
            raise QuotaExceeded(
                f"Quota exceeded for {user_id}:{kind}: would exceed limit of {limit}"
            )
        return result

    async def release(self, user_id: str, *, kind: str, amount: int) -> None:
        """Decrement usage (e.g. when a concurrent execution finishes)."""
        key = self._key(user_id, kind)
        await self.redis.decrby(key, amount)

    async def get_usage(self, user_id: str) -> QuotaUsage:
        """Return a snapshot of the user's current usage."""
        tokens_raw = await self.redis.get(self._key(user_id, "tokens_daily"))
        exec_raw = await self.redis.get(self._key(user_id, "executions_concurrent"))
        storage_raw = await self.redis.get(self._key(user_id, "storage_bytes"))
        return QuotaUsage(
            tokens_daily=int(tokens_raw) if tokens_raw else 0,
            executions_concurrent=int(exec_raw) if exec_raw else 0,
            storage_bytes=int(storage_raw) if storage_raw else 0,
        )
