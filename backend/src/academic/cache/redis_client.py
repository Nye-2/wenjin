"""Redis client for Wenjin caching and queue operations."""

import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import redis.asyncio as redis

from src.config import redis_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for academic caching operations."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or redis_settings.url
        self._settings = redis_settings
        self._client: Any | None = None
        self._owner_pid = os.getpid()

    def _build_client(self) -> Any:
        """Build a fresh Redis client for the current process."""
        return cast(Any, redis.from_url)(
            self.url,
            decode_responses=True,
            max_connections=self._settings.max_connections,
        )

    def _forked_from_owner(self) -> bool:
        """Return whether the client state was inherited across a process fork."""
        return self._owner_pid != os.getpid()

    async def reset_client(self, *, close_current: bool = True) -> None:
        """Reset the cached Redis client so the current process gets a fresh one."""
        current_client = self._client
        self._client = None
        self._owner_pid = os.getpid()

        if not close_current or current_client is None:
            return

        close_method = getattr(current_client, "aclose", None)
        if callable(close_method):
            await close_method()
        else:
            await current_client.close()

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._forked_from_owner():
            logger.info("Resetting Redis client after process fork")
            await self.reset_client(close_current=False)

        if self._client is None:
            self._client = self._build_client()

        try:
            await self._client.ping()
        except RuntimeError as exc:
            if "attached to a different loop" not in str(exc):
                await self.disconnect()
                raise
            logger.warning("Redis client loop affinity changed; rebuilding client")
            await self.reset_client(close_current=False)
            self._client = self._build_client()
            await self._client.ping()
        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self.reset_client(close_current=True)

    async def ping(self) -> bool:
        """Check whether Redis is reachable."""
        if self._client is None:
            await self.connect()
        return bool(await self.client.ping())

    @property
    def client(self) -> Any:
        """Get Redis client, connecting if necessary."""
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    # Key formatters
    @staticmethod
    def _rag_cache_key(workspace_id: str, query_hash: str) -> str:
        return f"rag:workspace:{workspace_id}:query:{query_hash}"

    @staticmethod
    def _agent_status_key(thread_id: str) -> str:
        return f"agent:thread:{thread_id}:status"

    @staticmethod
    def _sse_buffer_key(thread_id: str) -> str:
        return f"sse:thread:{thread_id}:buffer"

    @staticmethod
    def _workspace_lock_key(workspace_id: str) -> str:
        return f"lock:workspace:{workspace_id}:write"

    @staticmethod
    def _tier2_queue_key() -> str:
        return "tier2:extraction:queue"

    # RAG Cache operations
    async def get_rag_cache(
        self,
        workspace_id: str,
        query_hash: str,
    ) -> dict[str, Any] | None:
        """Get cached RAG results."""
        key = self._rag_cache_key(workspace_id, query_hash)
        data = await self.client.get(key)
        if not data:
            return None
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else None

    async def set_rag_cache(
        self,
        workspace_id: str,
        query_hash: str,
        results: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Cache RAG results with TTL."""
        key = self._rag_cache_key(workspace_id, query_hash)
        ttl = ttl or self._settings.llm_cache_ttl
        await self.client.setex(key, ttl, json.dumps(results))

    # Agent status operations
    async def set_agent_status(
        self,
        thread_id: str,
        status: str,
        skill: str | None = None,
        skill_name: str | None = None,
        subagent_count: int | None = None,
        clear_skill: bool = False,
    ) -> None:
        """Set agent status for a thread."""
        key = self._agent_status_key(thread_id)
        mapping: dict[str, str | int] = {"status": status}
        if clear_skill:
            await self.client.hdel(key, "current_skill", "current_skill_name")
        elif skill is not None:
            mapping["current_skill"] = skill
        if skill_name is not None:
            mapping["current_skill_name"] = skill_name
        if subagent_count is not None:
            mapping["subagent_count"] = subagent_count
        await self.client.hset(key, mapping=mapping)

    async def get_agent_status(self, thread_id: str) -> dict[str, str] | None:
        """Get agent status for a thread."""
        key = self._agent_status_key(thread_id)
        data = await self.client.hgetall(key)
        return cast(dict[str, str], data) if data else None

    # SSE buffer operations
    async def append_sse_event(self, thread_id: str, event: str, max_size: int = 100) -> None:
        """Append SSE event to buffer (capped)."""
        key = self._sse_buffer_key(thread_id)
        await self.client.lpush(key, event)
        await self.client.ltrim(key, 0, max_size - 1)
        await self.client.expire(key, 1800)  # 30 min TTL

    async def get_sse_buffer(self, thread_id: str, count: int = 50) -> list[str]:
        """Get recent SSE events from buffer."""
        key = self._sse_buffer_key(thread_id)
        return cast(list[str], await self.client.lrange(key, 0, count - 1))

    # Workspace lock operations
    @asynccontextmanager
    async def workspace_lock(
        self,
        workspace_id: str,
        timeout: int | None = None,
    ) -> AsyncGenerator[None, None]:
        """Acquire workspace write lock as context manager."""
        key = self._workspace_lock_key(workspace_id)
        timeout = timeout or self._settings.generation_lock_ttl
        token = uuid.uuid4().hex
        acquired = await self.client.set(key, token, nx=True, ex=timeout)
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for workspace {workspace_id}")
        try:
            yield
        finally:
            try:
                await self.client.eval(
                    """
                    if redis.call('get', KEYS[1]) == ARGV[1] then
                        return redis.call('del', KEYS[1])
                    end
                    return 0
                    """,
                    1,
                    key,
                    token,
                )
            except Exception:
                logger.exception(f"Failed to release workspace lock for {workspace_id}")

    # Tier2 extraction queue operations
    async def enqueue_extraction(self, paper_id: str) -> None:
        """Add paper to Tier2 extraction queue."""
        await self.client.rpush(self._tier2_queue_key(), paper_id)

    async def dequeue_extraction(self, timeout: int = 5) -> str | None:
        """Get next paper from Tier2 extraction queue (blocking)."""
        result = await self.client.blpop([self._tier2_queue_key()], timeout=timeout)
        return result[1] if result else None


# Global Redis client instance
redis_client = RedisClient()
