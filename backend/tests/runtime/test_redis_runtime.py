"""Tests for Redis-backed run runtime components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.runtime.chat_turns import ChatTurnConflictError, ChatTurnRunManager, ChatTurnRunStatus
from src.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, RedisStreamBridge


def _stream_id_parts(stream_id: str) -> tuple[int, int]:
    left, right = stream_id.split("-", 1)
    return int(left), int(right)


class FakeRedisPipeline:
    def __init__(self, backend: FakeRedisBackend) -> None:
        self._backend = backend
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self._ops.append(("hset", (key,), {"mapping": mapping}))

    def hgetall(self, key: str) -> None:
        self._ops.append(("hgetall", (key,), {}))

    def expire(self, key: str, ttl: int) -> None:
        self._ops.append(("expire", (key, ttl), {}))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._ops.append(("zadd", (key,), {"mapping": mapping}))

    def zrem(self, key: str, member: str) -> None:
        self._ops.append(("zrem", (key, member), {}))

    def delete(self, key: str) -> None:
        self._ops.append(("delete", (key,), {}))

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args, kwargs in self._ops:
            fn = getattr(self._backend, name)
            results.append(await fn(*args, **kwargs))
        self._ops.clear()
        return results


@dataclass
class _StreamEntry:
    stream_id: str
    fields: dict[str, str]


class FakeRedisBackend:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._sorted_sets: dict[str, dict[str, float]] = {}
        self._streams: dict[str, list[_StreamEntry]] = {}
        self._strings: dict[str, str] = {}
        self._stream_seq = 0

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self._hashes[key] = dict(mapping)
        return 1

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def expire(self, _key: str, _ttl: int) -> int:
        return 1

    async def zadd(self, key: str, *, mapping: dict[str, float]) -> int:
        bucket = self._sorted_sets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return len(mapping)

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        bucket = self._sorted_sets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda item: item[1], reverse=True)
        if stop < 0:
            stop = len(ordered) + stop
        if stop < start:
            return []
        return [member for member, _score in ordered[start: stop + 1]]

    async def zrem(self, key: str, member: str) -> int:
        bucket = self._sorted_sets.get(key, {})
        existed = 1 if member in bucket else 0
        bucket.pop(member, None)
        return existed

    async def delete(self, key: str) -> int:
        existed = 1 if key in self._hashes or key in self._streams or key in self._strings else 0
        self._hashes.pop(key, None)
        self._streams.pop(key, None)
        self._strings.pop(key, None)
        return existed

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,  # noqa: ARG002
    ) -> bool:
        if nx and key in self._strings:
            return False
        self._strings[key] = str(value)
        return True

    async def eval(
        self,
        script: str,  # noqa: ARG002
        numkeys: int,
        key: str,
        token: str,
    ) -> int:
        if numkeys != 1:
            return 0
        if self._strings.get(key) == token:
            self._strings.pop(key, None)
            return 1
        return 0

    async def xadd(
        self,
        key: str,
        *,
        fields: dict[str, str],
        maxlen: int | None = None,
        approximate: bool = True,  # noqa: ARG002
    ) -> str:
        self._stream_seq += 1
        stream_id = f"{self._stream_seq}-0"
        bucket = self._streams.setdefault(key, [])
        bucket.append(_StreamEntry(stream_id=stream_id, fields=dict(fields)))
        if maxlen is not None and len(bucket) > maxlen:
            overflow = len(bucket) - maxlen
            del bucket[:overflow]
        return stream_id

    async def xread(
        self,
        *,
        streams: dict[str, str],
        count: int = 100,
        block: int = 0,  # noqa: ARG002
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        [(key, cursor)] = list(streams.items())
        cursor_parts = _stream_id_parts(cursor)
        entries = []
        for entry in self._streams.get(key, []):
            if _stream_id_parts(entry.stream_id) > cursor_parts:
                entries.append((entry.stream_id, dict(entry.fields)))
            if len(entries) >= count:
                break
        if not entries:
            return []
        return [(key, entries)]


@pytest.mark.asyncio
async def test_run_manager_hydrates_from_redis_and_recovers_inflight_runs():
    backend = FakeRedisBackend()
    manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    created = await manager.create_or_reject("thread-1")
    await manager.set_status(created.run_id, ChatTurnRunStatus.running)

    recovered = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    await recovered.hydrate_recent(limit=50)

    loaded = recovered.get(created.run_id)
    assert loaded is not None
    assert loaded.status == ChatTurnRunStatus.interrupted
    assert loaded.error is not None
    assert "restarted" in loaded.error.lower()


@pytest.mark.asyncio
async def test_run_manager_refresh_updates_stale_in_memory_record():
    backend = FakeRedisBackend()
    manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    created = await manager.create_or_reject("thread-1")

    # Simulate another process updating terminal status in Redis only.
    run_key = f"runtime:chat_turns:{created.run_id}"
    backend._hashes[run_key]["status"] = ChatTurnRunStatus.success.value
    backend._hashes[run_key]["updated_at"] = "2026-04-15T00:00:00+00:00"

    stale = manager.get(created.run_id)
    assert stale is not None
    assert stale.status == ChatTurnRunStatus.pending

    refreshed = await manager.get_or_load(created.run_id, refresh=True)
    assert refreshed is not None
    assert refreshed.status == ChatTurnRunStatus.success


@pytest.mark.asyncio
async def test_run_manager_cancel_respects_refreshed_terminal_status():
    backend = FakeRedisBackend()
    manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    created = await manager.create_or_reject("thread-1")

    # Mark success in Redis before cancel attempt to emulate remote completion.
    run_key = f"runtime:chat_turns:{created.run_id}"
    backend._hashes[run_key]["status"] = ChatTurnRunStatus.success.value
    backend._hashes[run_key]["updated_at"] = "2026-04-15T00:00:00+00:00"

    cancelled = await manager.cancel(created.run_id)
    assert cancelled is False
    latest = await manager.get_or_load(created.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.success


@pytest.mark.asyncio
async def test_list_by_thread_refreshes_existing_cached_status():
    backend = FakeRedisBackend()
    manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    created = await manager.create_or_reject("thread-1")

    run_key = f"runtime:chat_turns:{created.run_id}"
    backend._hashes[run_key]["status"] = ChatTurnRunStatus.success.value
    backend._hashes[run_key]["updated_at"] = "2026-04-15T00:00:00+00:00"

    listed = await manager.list_by_thread("thread-1")
    assert listed
    assert listed[0].status == ChatTurnRunStatus.success


@pytest.mark.asyncio
async def test_create_or_reject_checks_redis_thread_index_for_inflight_conflict():
    backend = FakeRedisBackend()
    first_manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    created = await first_manager.create_or_reject("thread-1")
    await first_manager.set_status(created.run_id, ChatTurnRunStatus.running)

    # New process-local manager with empty memory should still see conflict.
    second_manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    with pytest.raises(ChatTurnConflictError):
        await second_manager.create_or_reject("thread-1", multitask_strategy="reject")


@pytest.mark.asyncio
async def test_create_or_reject_rejects_when_thread_scheduling_lock_is_held():
    backend = FakeRedisBackend()
    await backend.set("runtime:chat_turns:lock:thread:thread-1", "busy-token", nx=True, ex=5)
    manager = ChatTurnRunManager(redis_backend=backend, chat_turn_ttl_seconds=3600)
    manager._thread_lock_wait_seconds = 0.05
    manager._thread_lock_retry_seconds = 0.01

    with pytest.raises(ChatTurnConflictError, match="busy with run scheduling"):
        await manager.create_or_reject("thread-1")


@pytest.mark.asyncio
async def test_redis_stream_bridge_replay_and_end_event():
    backend = FakeRedisBackend()
    bridge = RedisStreamBridge(backend, queue_maxsize=16)
    run_id = "run-replay"

    await bridge.publish(run_id, "content", {"n": 1})
    await bridge.publish(run_id, "content", {"n": 2})
    await bridge.publish_end(run_id)

    consumed = []
    async for item in bridge.subscribe(run_id):
        consumed.append(item)

    assert len(consumed) == 3
    assert consumed[0].data == {"n": 1}
    assert consumed[1].data == {"n": 2}
    assert consumed[2] is END_SENTINEL

    replayed = []
    async for item in bridge.subscribe(run_id, last_event_id=consumed[0].id):
        replayed.append(item)

    assert len(replayed) == 2
    assert replayed[0].data == {"n": 2}
    assert replayed[1] is END_SENTINEL


@pytest.mark.asyncio
async def test_redis_stream_bridge_emits_heartbeat_when_idle():
    backend = FakeRedisBackend()
    bridge = RedisStreamBridge(backend, queue_maxsize=8)
    run_id = "run-heartbeat"

    subscriber = bridge.subscribe(run_id, heartbeat_interval=0.01)
    heartbeat = await anext(subscriber)
    assert heartbeat is HEARTBEAT_SENTINEL

    await bridge.publish_end(run_id)
    end = await anext(subscriber)
    assert end is END_SENTINEL
