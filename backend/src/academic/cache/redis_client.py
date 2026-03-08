"""Redis client for AcademiaGPT caching and queue operations."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis

from src.config import settings


class RedisClient:
    """Redis client for academic caching operations."""

    def __init__(self, url: str = None):
        self.url = url or settings.redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._client is None:
            self._client = redis.from_url(self.url, decode_responses=True)

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> redis.Redis:
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
    async def get_rag_cache(self, workspace_id: str, query_hash: str) -> dict | None:
        """Get cached RAG results."""
        key = self._rag_cache_key(workspace_id, query_hash)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def set_rag_cache(
        self, workspace_id: str, query_hash: str, results: dict, ttl: int = 3600
    ) -> None:
        """Cache RAG results with TTL (default 1 hour)."""
        key = self._rag_cache_key(workspace_id, query_hash)
        await self.client.setex(key, ttl, json.dumps(results))

    # Agent status operations
    async def set_agent_status(
        self, thread_id: str, status: str, skill: str = None, subagent_count: int = 0
    ) -> None:
        """Set agent status for a thread."""
        key = self._agent_status_key(thread_id)
        await self.client.hset(key, mapping={
            "status": status,
            "current_skill": skill or "",
            "subagent_count": subagent_count,
        })

    async def get_agent_status(self, thread_id: str) -> dict | None:
        """Get agent status for a thread."""
        key = self._agent_status_key(thread_id)
        data = await self.client.hgetall(key)
        return data if data else None

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
        return await self.client.lrange(key, 0, count - 1)

    # Workspace lock operations
    @asynccontextmanager
    async def workspace_lock(self, workspace_id: str, timeout: int = 30) -> AsyncGenerator[None, None]:
        """Acquire workspace write lock as context manager."""
        key = self._workspace_lock_key(workspace_id)
        acquired = await self.client.set(key, "locked", nx=True, ex=timeout)
        try:
            if not acquired:
                raise RuntimeError(f"Could not acquire lock for workspace {workspace_id}")
            yield
        finally:
            await self.client.delete(key)

    # Tier2 extraction queue operations
    async def enqueue_extraction(self, paper_id: str) -> None:
        """Add paper to Tier2 extraction queue."""
        await self.client.rpush(self._tier2_queue_key(), paper_id)

    async def dequeue_extraction(self, timeout: int = 5) -> str | None:
        """Get next paper from Tier2 extraction queue (blocking)."""
        result = await self.client.blpop(self._tier2_queue_key(), timeout=timeout)
        return result[1] if result else None


# Global Redis client instance
redis_client = RedisClient()
