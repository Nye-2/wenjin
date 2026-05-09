"""Event bus — Redis pub/sub wrapper."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Redis-backed pub/sub event bus.

    Handlers are registered via :meth:`subscribe` and invoked for every
    message published to the corresponding channel.
    """

    def __init__(self, redis) -> None:
        self.redis = redis
        self._handlers: dict[str, list[Callable]] = {}
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    def subscribe(self, channel: str, handler: Callable) -> None:
        """Register *handler* to be called for messages on *channel*."""
        self._handlers.setdefault(channel, []).append(handler)

    async def publish(self, channel: str, event: dict) -> int:
        """Publish *event* to *channel*. Returns the number of subscribers."""
        return await self.redis.publish(channel, json.dumps(event))

    async def start(self) -> None:
        """Start the background listener task."""
        self._pubsub = self.redis.pubsub()
        if self._handlers:
            await self._pubsub.subscribe(*self._handlers.keys())
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop the listener task and close the pubsub connection."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

    async def _listen(self) -> None:
        """Background loop that dispatches messages to handlers."""
        assert self._pubsub is not None
        while True:
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0,
            )
            if message and message["type"] == "message":
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                data = message["data"]
                if isinstance(data, bytes):
                    data = json.loads(data)
                elif isinstance(data, str):
                    data = json.loads(data)
                for handler in self._handlers.get(channel, []):
                    try:
                        await handler(data)
                    except Exception:
                        logger.warning(
                            "Handler failed for channel=%s", channel, exc_info=True,
                        )
            await asyncio.sleep(0.01)
