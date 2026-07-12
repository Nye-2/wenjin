"""ChatTurnRun registry with optional TTL-bound Redis transport state."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .schemas import ChatTurnDisconnectMode, ChatTurnRunStatus

logger = logging.getLogger(__name__)


class ChatTurnConflictError(Exception):
    """Raised when multitask_strategy=reject and a thread already has inflight runs."""


class UnsupportedChatTurnStrategyError(Exception):
    """Raised when multitask strategy is unsupported."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChatTurnRunRecord:
    """Mutable in-memory run record."""

    run_id: str
    thread_id: str
    assistant_id: str | None
    status: ChatTurnRunStatus
    on_disconnect: ChatTurnDisconnectMode
    multitask_strategy: str = "reject"
    metadata: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    task: asyncio.Task[Any] | None = field(default=None, repr=False)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    abort_action: str = "interrupt"
    error: str | None = None


class ChatTurnRunManager:
    """Thread-safe run registry.

    In worker-dispatched mode, active run execution lives outside the gateway
    process and records may have no local task handle.
    When a Redis backend is provided, run metadata is mirrored to Redis so
    records survive gateway restarts and can be reloaded on boot.
    """

    def __init__(
        self,
        *,
        redis_backend: Any | None = None,
        chat_turn_ttl_seconds: int = 86400,
    ) -> None:
        self._chat_turns: dict[str, ChatTurnRunRecord] = {}
        self._lock = asyncio.Lock()
        self._redis = redis_backend
        self._chat_turn_ttl_seconds = min(3600, max(300, int(chat_turn_ttl_seconds)))
        self._thread_lock_ttl_seconds = 5
        self._thread_lock_wait_seconds = 1.0
        self._thread_lock_retry_seconds = 0.05

    @staticmethod
    def _chat_turn_key(run_id: str) -> str:
        return f"runtime:chat_turns:{run_id}"

    @staticmethod
    def _all_index_key() -> str:
        return "runtime:chat_turns:index:all"

    @staticmethod
    def _thread_index_key(thread_id: str) -> str:
        return f"runtime:chat_turns:index:thread:{thread_id}"

    @staticmethod
    def _thread_lock_key(thread_id: str) -> str:
        return f"runtime:chat_turns:lock:thread:{thread_id}"

    @staticmethod
    def _score_from_iso(timestamp: str) -> float:
        try:
            return datetime.fromisoformat(timestamp).timestamp()
        except Exception:
            return datetime.now(UTC).timestamp()

    @staticmethod
    def _json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return "{}"

    @staticmethod
    def _json_loads(value: Any, default: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, str) or not value:
            return dict(default)
        try:
            parsed = json.loads(value)
        except Exception:
            return dict(default)
        if isinstance(parsed, Mapping):
            return dict(parsed)
        return dict(default)

    def _record_to_mapping(self, record: ChatTurnRunRecord) -> dict[str, str]:
        return {
            "run_id": record.run_id,
            "thread_id": record.thread_id,
            "assistant_id": str(record.assistant_id or ""),
            "status": record.status.value,
            "on_disconnect": record.on_disconnect.value,
            "multitask_strategy": record.multitask_strategy,
            "metadata": self._json_dumps(record.metadata),
            "kwargs": self._json_dumps(record.kwargs),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "abort_action": record.abort_action,
            "error": str(record.error or ""),
        }

    def _mapping_to_record(self, mapping: Mapping[str, Any]) -> ChatTurnRunRecord | None:
        run_id = str(mapping.get("run_id") or "").strip()
        thread_id = str(mapping.get("thread_id") or "").strip()
        if not run_id or not thread_id:
            return None

        raw_status = str(mapping.get("status") or ChatTurnRunStatus.error.value).strip()
        raw_disconnect = str(mapping.get("on_disconnect") or ChatTurnDisconnectMode.cancel.value).strip()
        try:
            status = ChatTurnRunStatus(raw_status)
        except Exception:
            status = ChatTurnRunStatus.error
        try:
            on_disconnect = ChatTurnDisconnectMode(raw_disconnect)
        except Exception:
            on_disconnect = ChatTurnDisconnectMode.cancel

        return ChatTurnRunRecord(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=(str(mapping.get("assistant_id") or "").strip() or None),
            status=status,
            on_disconnect=on_disconnect,
            multitask_strategy=str(mapping.get("multitask_strategy") or "reject"),
            metadata=self._json_loads(mapping.get("metadata"), {}),
            kwargs=self._json_loads(mapping.get("kwargs"), {}),
            created_at=str(mapping.get("created_at") or _now_iso()),
            updated_at=str(mapping.get("updated_at") or _now_iso()),
            abort_action=str(mapping.get("abort_action") or "interrupt"),
            error=(str(mapping.get("error") or "").strip() or None),
        )

    async def _persist_record(
        self,
        record: ChatTurnRunRecord,
        *,
        previous_thread_id: str | None = None,
    ) -> None:
        if self._redis is None:
            return

        run_id = record.run_id
        run_key = self._chat_turn_key(run_id)
        score = self._score_from_iso(record.created_at or _now_iso())

        try:
            pipe = self._redis.pipeline()
            pipe.hset(run_key, mapping=self._record_to_mapping(record))
            pipe.expire(run_key, self._chat_turn_ttl_seconds)

            all_index = self._all_index_key()
            pipe.zadd(all_index, {run_id: score})
            pipe.expire(all_index, self._chat_turn_ttl_seconds)

            if previous_thread_id and previous_thread_id != record.thread_id:
                pipe.zrem(self._thread_index_key(previous_thread_id), run_id)

            thread_index = self._thread_index_key(record.thread_id)
            pipe.zadd(thread_index, {run_id: score})
            pipe.expire(thread_index, self._chat_turn_ttl_seconds)
            await pipe.execute()
        except Exception:
            logger.warning("Failed to persist run %s into Redis", run_id, exc_info=True)

    async def _load_record_from_redis(self, run_id: str) -> ChatTurnRunRecord | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.hgetall(self._chat_turn_key(run_id))
        except Exception:
            logger.warning("Failed to load run %s from Redis", run_id, exc_info=True)
            return None
        if not raw:
            return None
        loaded = self._mapping_to_record(raw)
        if loaded is None:
            return None
        return await self._merge_loaded_record(loaded)

    async def _merge_loaded_record(self, loaded: ChatTurnRunRecord) -> ChatTurnRunRecord:
        """Merge one Redis-loaded record while preserving local task handles."""
        async with self._lock:
            existing = self._chat_turns.get(loaded.run_id)
            if existing is not None:
                # Keep process-local control handles while refreshing status/data
                # from Redis, which is the cross-process source of truth.
                existing.thread_id = loaded.thread_id
                existing.assistant_id = loaded.assistant_id
                existing.status = loaded.status
                existing.on_disconnect = loaded.on_disconnect
                existing.multitask_strategy = loaded.multitask_strategy
                existing.metadata = loaded.metadata
                existing.kwargs = loaded.kwargs
                existing.created_at = loaded.created_at
                existing.updated_at = loaded.updated_at
                existing.abort_action = loaded.abort_action
                existing.error = loaded.error
                if loaded.status == ChatTurnRunStatus.interrupted:
                    existing.abort_event.set()
                return existing
            if loaded.status == ChatTurnRunStatus.interrupted:
                loaded.abort_event.set()
            self._chat_turns[loaded.run_id] = loaded
            return loaded

    async def _load_records_from_redis(self, run_ids: list[str]) -> None:
        """Batch-load multiple run records from Redis into local memory."""
        if self._redis is None:
            return
        normalized = [str(item).strip() for item in run_ids if str(item).strip()]
        if not normalized:
            return
        try:
            pipe = self._redis.pipeline()
            for run_id in normalized:
                pipe.hgetall(self._chat_turn_key(run_id))
            rows = await pipe.execute()
        except Exception:
            logger.warning("Failed to batch load runs from Redis", exc_info=True)
            for run_id in normalized:
                await self._load_record_from_redis(run_id)
            return

        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            loaded = self._mapping_to_record(raw)
            if loaded is None:
                continue
            await self._merge_loaded_record(loaded)

    async def _delete_record_from_redis(self, run_id: str, *, thread_id: str | None) -> None:
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.delete(self._chat_turn_key(run_id))
            pipe.zrem(self._all_index_key(), run_id)
            if thread_id:
                pipe.zrem(self._thread_index_key(thread_id), run_id)
            await pipe.execute()
        except Exception:
            logger.warning("Failed to cleanup run %s from Redis", run_id, exc_info=True)

    async def _load_thread_chat_turns_from_redis(self, thread_id: str, *, limit: int = 64) -> None:
        """Hydrate recent runs for one thread from Redis into local memory."""
        if self._redis is None:
            return
        normalized = str(thread_id).strip()
        if not normalized:
            return
        try:
            run_ids = await self._redis.zrevrange(
                self._thread_index_key(normalized),
                0,
                max(1, int(limit)) - 1,
            )
        except Exception:
            return
        await self._load_records_from_redis([str(item) for item in run_ids])

    def _supports_thread_lock(self) -> bool:
        if self._redis is None:
            return False
        return callable(getattr(self._redis, "set", None)) and callable(
            getattr(self._redis, "eval", None)
        )

    async def _acquire_thread_scheduling_lock(self, thread_id: str) -> str | None:
        """Acquire best-effort distributed lock for one thread scheduling window."""
        if not self._supports_thread_lock():
            return None

        key = self._thread_lock_key(thread_id)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + self._thread_lock_wait_seconds
        while time.monotonic() < deadline:
            try:
                acquired = await self._redis.set(  # type: ignore[union-attr]
                    key,
                    token,
                    nx=True,
                    ex=self._thread_lock_ttl_seconds,
                )
            except Exception:
                logger.warning(
                    "Failed to acquire run scheduling lock for thread %s",
                    thread_id,
                    exc_info=True,
                )
                return None
            if acquired:
                return token
            await asyncio.sleep(self._thread_lock_retry_seconds)
        raise ChatTurnConflictError(
            f"Thread {thread_id} is busy with run scheduling; please retry"
        )

    async def _release_thread_scheduling_lock(self, thread_id: str, token: str | None) -> None:
        if token is None or not self._supports_thread_lock():
            return
        key = self._thread_lock_key(thread_id)
        try:
            await self._redis.eval(  # type: ignore[union-attr]
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
            logger.warning(
                "Failed to release run scheduling lock for thread %s",
                thread_id,
                exc_info=True,
            )

    async def hydrate_recent(self, *, limit: int = 300) -> None:
        """Load recent run metadata from Redis into local memory."""
        if self._redis is None:
            return
        capped_limit = max(10, int(limit))
        try:
            run_ids = await self._redis.zrevrange(self._all_index_key(), 0, capped_limit - 1)
        except Exception:
            logger.warning("Failed to read run index from Redis", exc_info=True)
            return
        if not run_ids:
            return

        try:
            pipe = self._redis.pipeline()
            for run_id in run_ids:
                pipe.hgetall(self._chat_turn_key(str(run_id)))
            rows = await pipe.execute()
        except Exception:
            logger.warning("Failed to hydrate run records from Redis", exc_info=True)
            return

        now = _now_iso()
        persisted_updates: list[ChatTurnRunRecord] = []
        async with self._lock:
            for raw in reversed(rows):
                if not isinstance(raw, Mapping):
                    continue
                record = self._mapping_to_record(raw)
                if record is None:
                    continue
                # Runs cannot continue across gateway process restarts.
                if record.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running):
                    record.status = ChatTurnRunStatus.interrupted
                    record.error = record.error or "Gateway restarted during run execution"
                    record.updated_at = now
                    persisted_updates.append(record)
                self._chat_turns[record.run_id] = record

        for record in persisted_updates:
            await self._persist_record(record)

    def get(self, run_id: str) -> ChatTurnRunRecord | None:
        return self._chat_turns.get(run_id)

    async def get_or_load(self, run_id: str, *, refresh: bool = False) -> ChatTurnRunRecord | None:
        """Get a run record from memory, or lazily load/refresh it from Redis."""
        if refresh and self._redis is not None:
            loaded = await self._load_record_from_redis(run_id)
            if loaded is not None:
                return loaded
            return self._chat_turns.get(run_id)
        record = self._chat_turns.get(run_id)
        if record is not None:
            return record
        return await self._load_record_from_redis(run_id)

    async def list_by_thread(self, thread_id: str) -> list[ChatTurnRunRecord]:
        normalized = str(thread_id).strip()
        if not normalized:
            return []

        if self._redis is not None:
            try:
                run_ids = await self._redis.zrevrange(self._thread_index_key(normalized), 0, 199)
            except Exception:
                run_ids = []
            await self._load_records_from_redis([str(item) for item in run_ids])
            if run_ids:
                ordered = [self._chat_turns[str(run_id)] for run_id in run_ids if str(run_id) in self._chat_turns]
                if ordered:
                    return ordered

        async with self._lock:
            return [
                record
                for record in reversed(self._chat_turns.values())
                if record.thread_id == normalized
            ]

    async def list_all(self) -> list[ChatTurnRunRecord]:
        """Return all runs ordered by most recently created first."""
        if self._redis is not None:
            try:
                run_ids = await self._redis.zrevrange(self._all_index_key(), 0, 199)
            except Exception:
                run_ids = []
            await self._load_records_from_redis([str(item) for item in run_ids])
            if run_ids:
                ordered = [self._chat_turns[str(run_id)] for run_id in run_ids if str(run_id) in self._chat_turns]
                if ordered:
                    return ordered

        async with self._lock:
            return list(reversed(self._chat_turns.values()))

    async def set_status(self, run_id: str, status: ChatTurnRunStatus, *, error: str | None = None) -> None:
        record = await self.get_or_load(run_id)
        if record is None:
            return

        async with self._lock:
            record = self._chat_turns.get(run_id)
            if record is None:
                return
            record.status = status
            record.updated_at = _now_iso()
            if error is not None:
                record.error = error
            snapshot = record

        await self._persist_record(snapshot)

    async def bind_thread(self, run_id: str, thread_id: str) -> None:
        """Bind a run to its resolved thread once preparation finishes."""
        normalized = str(thread_id).strip()
        if not normalized:
            return

        record = await self.get_or_load(run_id)
        if record is None:
            return

        async with self._lock:
            record = self._chat_turns.get(run_id)
            if record is None:
                return
            previous_thread_id = record.thread_id
            record.thread_id = normalized
            record.updated_at = _now_iso()
            snapshot = record

        await self._persist_record(snapshot, previous_thread_id=previous_thread_id)

    async def create_or_reject(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: ChatTurnDisconnectMode = ChatTurnDisconnectMode.cancel,
        metadata: dict[str, Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        multitask_strategy: str = "reject",
    ) -> ChatTurnRunRecord:
        run_id = str(uuid.uuid4())
        now = _now_iso()
        supported = ("reject", "interrupt", "rollback")
        normalized_thread_id = str(thread_id).strip() or run_id
        lock_token = await self._acquire_thread_scheduling_lock(normalized_thread_id)
        try:
            # In distributed mode, ensure local memory sees recent thread runs
            # before applying multitask_strategy decisions.
            await self._load_thread_chat_turns_from_redis(normalized_thread_id)

            persisted_updates: list[ChatTurnRunRecord] = []
            async with self._lock:
                if multitask_strategy not in supported:
                    raise UnsupportedChatTurnStrategyError(
                        f"Multitask strategy '{multitask_strategy}' is not supported. "
                        f"Supported strategies: {', '.join(supported)}"
                    )

                inflight = [
                    record
                    for record in self._chat_turns.values()
                    if record.thread_id == normalized_thread_id
                    and record.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running)
                ]

                if multitask_strategy == "reject" and inflight:
                    raise ChatTurnConflictError(
                        f"Thread {normalized_thread_id} already has an active run"
                    )

                if multitask_strategy in ("interrupt", "rollback") and inflight:
                    for record in inflight:
                        record.abort_action = multitask_strategy
                        record.abort_event.set()
                        if record.task is not None and not record.task.done():
                            record.task.cancel()
                        record.status = ChatTurnRunStatus.interrupted
                        record.updated_at = now
                        persisted_updates.append(record)

                created = ChatTurnRunRecord(
                    run_id=run_id,
                    thread_id=normalized_thread_id,
                    assistant_id=assistant_id,
                    status=ChatTurnRunStatus.pending,
                    on_disconnect=on_disconnect,
                    multitask_strategy=multitask_strategy,
                    metadata=metadata or {},
                    kwargs=kwargs or {},
                    created_at=now,
                    updated_at=now,
                )
                self._chat_turns[run_id] = created
                persisted_updates.append(created)

            for record in persisted_updates:
                await self._persist_record(record)

            logger.info(
                "Run created: run_id=%s thread_id=%s",
                created.run_id,
                created.thread_id,
            )
            return created
        finally:
            await self._release_thread_scheduling_lock(normalized_thread_id, lock_token)

    async def cancel(self, run_id: str, *, action: str = "interrupt") -> bool:
        record = await self.get_or_load(run_id, refresh=True)
        if record is None:
            return False

        async with self._lock:
            record = self._chat_turns.get(run_id)
            if record is None:
                return False
            if record.status not in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running):
                return False
            record.abort_action = action
            record.abort_event.set()
            if record.task is not None and not record.task.done():
                record.task.cancel()
            record.status = ChatTurnRunStatus.interrupted
            record.updated_at = _now_iso()
            snapshot = record
        await self._persist_record(snapshot)
        return True

    async def is_abort_requested(self, run_id: str) -> bool:
        """Return whether the run has an active abort request."""
        record = await self.get_or_load(run_id, refresh=True)
        if record is None:
            return False
        if record.abort_event.is_set():
            return True

        if record.status == ChatTurnRunStatus.interrupted:
            record.abort_event.set()
            return True
        return False

    async def get_abort_action(self, run_id: str, *, default: str = "interrupt") -> str:
        """Return requested abort action for a run, defaulting to ``interrupt``."""
        record = await self.get_or_load(run_id, refresh=True)
        if record is None:
            return default
        action = str(record.abort_action or "").strip()
        if not action:
            return default
        return action

    async def update_metadata(self, run_id: str, values: Mapping[str, Any]) -> None:
        """Merge metadata fields for one run and persist the updated record."""
        if not values:
            return
        record = await self.get_or_load(run_id)
        if record is None:
            return

        async with self._lock:
            current = self._chat_turns.get(run_id)
            if current is None:
                return
            merged = dict(current.metadata)
            for key, value in values.items():
                merged[str(key)] = value
            current.metadata = merged
            current.updated_at = _now_iso()
            snapshot = current

        await self._persist_record(snapshot)

    async def cleanup(
        self,
        run_id: str,
        *,
        delay: float = 300.0,
        remove_persistent: bool = False,
    ) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        thread_id: str | None = None
        async with self._lock:
            removed = self._chat_turns.pop(run_id, None)
            if removed is not None:
                thread_id = removed.thread_id
        if remove_persistent:
            await self._delete_record_from_redis(run_id, thread_id=thread_id)
