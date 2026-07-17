"""Redis-backed stream bridge with replay support."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

try:
    from redis.exceptions import TimeoutError as RedisTimeoutError
except Exception:  # pragma: no cover - redis package always present in runtime
    RedisTimeoutError = TimeoutError  # type: ignore

from src.runtime.serialization import dumps_json

from .base import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge, StreamEvent


class RedisStreamBridge(StreamBridge):
    """Redis Streams implementation for run SSE fanout and replay."""

    def __init__(
        self,
        redis_backend: Any,
        *,
        queue_maxsize: int = 512,
        stream_ttl_seconds: int = 86400,
        key_prefix: str = "runtime:runs:stream",
    ) -> None:
        self._redis = redis_backend
        self._maxsize = max(1, int(queue_maxsize))
        self._stream_ttl_seconds = max(300, int(stream_ttl_seconds))
        self._key_prefix = key_prefix.rstrip(":")

    def _stream_key(self, run_id: str) -> str:
        return f"{self._key_prefix}:{run_id}"

    @staticmethod
    def _decode_payload(raw_data: Any) -> Any:
        if not isinstance(raw_data, str):
            return raw_data
        if not raw_data:
            return None
        try:
            return json.loads(raw_data)
        except Exception:
            return raw_data

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        key = self._stream_key(run_id)
        fields = {
            "event": str(event),
            "data": dumps_json(data, ensure_ascii=False),
        }
        await self._redis.xadd(
            key,
            fields=fields,
            maxlen=self._maxsize,
            approximate=True,
        )
        await self._redis.expire(key, self._stream_ttl_seconds)

    async def publish_end(self, run_id: str) -> None:
        key = self._stream_key(run_id)
        await self._redis.xadd(
            key,
            fields={
                "event": "__end__",
                "data": "null",
            },
            maxlen=self._maxsize,
            approximate=True,
        )
        await self._redis.expire(key, self._stream_ttl_seconds)

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        key = self._stream_key(run_id)
        cursor = str(last_event_id or "0-0")
        block_ms = max(1, int(heartbeat_interval * 1000))

        while True:
            try:
                records = await self._redis.xread(
                    streams={key: cursor},
                    count=100,
                    block=block_ms,
                )
            except (RedisTimeoutError, TimeoutError):
                # Treat network read timeout like an idle interval so SSE clients
                # keep receiving heartbeats instead of a hard stream failure.
                yield HEARTBEAT_SENTINEL
                continue
            if not records:
                yield HEARTBEAT_SENTINEL
                continue

            for _stream_name, entries in records:
                for event_id, fields in entries:
                    resolved_id = str(event_id)
                    cursor = resolved_id

                    event = str(fields.get("event") or "").strip()
                    if event == "__end__":
                        yield END_SENTINEL
                        return

                    payload = self._decode_payload(fields.get("data"))
                    yield StreamEvent(
                        id=resolved_id,
                        event=event or "message",
                        data=payload,
                    )
