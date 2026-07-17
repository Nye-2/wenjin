"""ChatTurnRun registry with optional TTL-bound Redis transport state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .schemas import (
    ChatTurnDisconnectMode,
    ChatTurnExecutionRenewal,
    ChatTurnRunStatus,
)

logger = logging.getLogger(__name__)

_REQUEST_KEY_METADATA = "_request_idempotency_key"
_REQUEST_FINGERPRINT_METADATA = "_request_fingerprint"


class ChatTurnConflictError(Exception):
    """Raised when multitask_strategy=reject and a thread already has inflight runs."""


class UnsupportedChatTurnStrategyError(Exception):
    """Raised when multitask strategy is unsupported."""


class ChatTurnTransportUnavailableError(RuntimeError):
    """Raised when Redis cannot durably admit or coordinate a chat turn."""


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
    execution_owner: str | None = field(default=None, repr=False)
    execution_lease_until: str | None = field(default=None, repr=False)
    dispatch_owner: str | None = field(default=None, repr=False)
    dispatch_lease_until: str | None = field(default=None, repr=False)
    worker_task_id: str | None = field(default=None, repr=False)
    dispatch_payload: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class ChatTurnRunAdmission:
    record: ChatTurnRunRecord
    created: bool


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
        execution_lease_seconds: float = 30.0,
        dispatch_lease_seconds: float = 5.0,
    ) -> None:
        self._chat_turns: dict[str, ChatTurnRunRecord] = {}
        self._lock = asyncio.Lock()
        self._local_scheduling_lock = asyncio.Lock()
        self._redis = redis_backend
        self._chat_turn_ttl_seconds = min(3600, max(300, int(chat_turn_ttl_seconds)))
        self._thread_lock_ttl_seconds = 5
        self._thread_lock_wait_seconds = 1.0
        self._thread_lock_retry_seconds = 0.05
        self._execution_lease_seconds = max(0.05, float(execution_lease_seconds))
        self._dispatch_lease_seconds = max(1.0, float(dispatch_lease_seconds))
        self._dispatch_claim_poll_seconds = min(
            0.1,
            max(0.02, self._dispatch_lease_seconds / 10),
        )
        self._execution_claim_poll_seconds = min(
            0.25,
            max(0.02, self._execution_lease_seconds / 4),
        )

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
    def _request_key_digest(request_key: str) -> str:
        return hashlib.sha256(str(request_key).encode()).hexdigest()

    @classmethod
    def _request_index_key(cls, request_key: str) -> str:
        return f"runtime:chat_turns:index:request:{cls._request_key_digest(request_key)}"

    @classmethod
    def _request_lock_key(cls, request_key: str) -> str:
        return f"runtime:chat_turns:lock:request:{cls._request_key_digest(request_key)}"

    @staticmethod
    def _dispatch_index_key() -> str:
        return "runtime:chat_turns:index:dispatch_pending"

    @staticmethod
    def _run_lock_key(run_id: str) -> str:
        return f"runtime:chat_turns:lock:run:{run_id}"

    @staticmethod
    def _score_from_iso(timestamp: str) -> float:
        try:
            return datetime.fromisoformat(timestamp).timestamp()
        except Exception:
            return datetime.now(UTC).timestamp()

    @staticmethod
    def _lease_is_expired(value: str | None, *, now: datetime) -> bool:
        if not value:
            return True
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed <= now

    @property
    def execution_lease_seconds(self) -> float:
        return self._execution_lease_seconds

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
            "execution_owner": str(record.execution_owner or ""),
            "execution_lease_until": str(record.execution_lease_until or ""),
            "dispatch_owner": str(record.dispatch_owner or ""),
            "dispatch_lease_until": str(record.dispatch_lease_until or ""),
            "worker_task_id": str(record.worker_task_id or ""),
            "dispatch_payload": self._json_dumps(record.dispatch_payload),
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
            execution_owner=(str(mapping.get("execution_owner") or "").strip() or None),
            execution_lease_until=(
                str(mapping.get("execution_lease_until") or "").strip() or None
            ),
            dispatch_owner=(str(mapping.get("dispatch_owner") or "").strip() or None),
            dispatch_lease_until=(
                str(mapping.get("dispatch_lease_until") or "").strip() or None
            ),
            worker_task_id=(str(mapping.get("worker_task_id") or "").strip() or None),
            dispatch_payload=self._json_loads(mapping.get("dispatch_payload"), {}),
        )

    async def _persist_record(
        self,
        record: ChatTurnRunRecord,
        *,
        previous_thread_id: str | None = None,
    ) -> bool:
        if self._redis is None:
            return True

        run_id = record.run_id
        run_key = self._chat_turn_key(run_id)
        score = self._score_from_iso(record.created_at or _now_iso())
        cutoff_score = datetime.now(UTC).timestamp() - self._chat_turn_ttl_seconds
        request_key = str(record.metadata.get(_REQUEST_KEY_METADATA) or "").strip()

        try:
            pipe = self._redis.pipeline()
            pipe.hset(run_key, mapping=self._record_to_mapping(record))
            pipe.expire(run_key, self._chat_turn_ttl_seconds)

            all_index = self._all_index_key()
            pipe.zadd(all_index, {run_id: score})
            pipe.zremrangebyscore(all_index, "-inf", cutoff_score)
            pipe.expire(all_index, self._chat_turn_ttl_seconds)

            if previous_thread_id and previous_thread_id != record.thread_id:
                pipe.zrem(self._thread_index_key(previous_thread_id), run_id)

            thread_index = self._thread_index_key(record.thread_id)
            pipe.zadd(thread_index, {run_id: score})
            pipe.zremrangebyscore(thread_index, "-inf", cutoff_score)
            pipe.expire(thread_index, self._chat_turn_ttl_seconds)

            dispatch_index = self._dispatch_index_key()
            if (
                record.status == ChatTurnRunStatus.pending
                and record.worker_task_id is None
            ):
                pipe.zadd(dispatch_index, {run_id: score})
            else:
                pipe.zrem(dispatch_index, run_id)
            pipe.zremrangebyscore(dispatch_index, "-inf", cutoff_score)
            pipe.expire(dispatch_index, self._chat_turn_ttl_seconds)

            if request_key:
                pipe.set(
                    self._request_index_key(request_key),
                    run_id,
                    ex=self._chat_turn_ttl_seconds,
                )
            await pipe.execute()
            return True
        except Exception:
            logger.warning("Failed to persist run %s into Redis", run_id, exc_info=True)
            return False

    async def _load_record_from_redis(self, run_id: str) -> ChatTurnRunRecord | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.hgetall(self._chat_turn_key(run_id))
        except Exception as exc:
            raise ChatTurnTransportUnavailableError(
                f"Chat turn {run_id} could not be loaded"
            ) from exc
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
                existing.execution_owner = loaded.execution_owner
                existing.execution_lease_until = loaded.execution_lease_until
                existing.dispatch_owner = loaded.dispatch_owner
                existing.dispatch_lease_until = loaded.dispatch_lease_until
                existing.worker_task_id = loaded.worker_task_id
                existing.dispatch_payload = loaded.dispatch_payload
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

    async def _delete_record_from_redis(
        self,
        run_id: str,
        *,
        thread_id: str | None,
        request_key: str | None,
    ) -> None:
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.delete(self._chat_turn_key(run_id))
            pipe.zrem(self._all_index_key(), run_id)
            pipe.zrem(self._dispatch_index_key(), run_id)
            if thread_id:
                pipe.zrem(self._thread_index_key(thread_id), run_id)
            if request_key:
                pipe.delete(self._request_index_key(request_key))
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
        except Exception as exc:
            raise ChatTurnTransportUnavailableError(
                f"Thread {normalized} chat-turn index is unavailable"
            ) from exc
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

    async def _acquire_request_scheduling_lock(
        self,
        request_key: str,
    ) -> str | None:
        if not self._supports_thread_lock():
            return None
        key = self._request_lock_key(request_key)
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
            except Exception as exc:
                raise ChatTurnTransportUnavailableError(
                    "Chat request scheduling state is unavailable"
                ) from exc
            if acquired:
                return token
            await asyncio.sleep(self._thread_lock_retry_seconds)
        raise ChatTurnConflictError("Chat request is already being scheduled; retry")

    async def _release_request_scheduling_lock(
        self,
        request_key: str,
        token: str | None,
    ) -> None:
        if token is None or not self._supports_thread_lock():
            return
        try:
            await self._redis.eval(  # type: ignore[union-attr]
                """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """,
                1,
                self._request_lock_key(request_key),
                token,
            )
        except Exception:
            logger.warning(
                "Failed to release chat request scheduling lock",
                exc_info=True,
            )

    async def _acquire_run_state_lock(self, run_id: str) -> str | None:
        if not self._supports_thread_lock():
            return None
        key = self._run_lock_key(run_id)
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
                    "Failed to acquire run state lock for run %s",
                    run_id,
                    exc_info=True,
                )
                return None
            if acquired:
                return token
            await asyncio.sleep(self._thread_lock_retry_seconds)
        return None

    async def _release_run_state_lock(self, run_id: str, token: str | None) -> None:
        if token is None or not self._supports_thread_lock():
            return
        try:
            await self._redis.eval(  # type: ignore[union-attr]
                """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """,
                1,
                self._run_lock_key(run_id),
                token,
            )
        except Exception:
            logger.warning(
                "Failed to release run state lock for run %s",
                run_id,
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

        async with self._lock:
            for raw in reversed(rows):
                if not isinstance(raw, Mapping):
                    continue
                record = self._mapping_to_record(raw)
                if record is None:
                    continue
                self._chat_turns[record.run_id] = record

    def _prune_local_expired_locked(self, *, now: datetime | None = None) -> None:
        """Bound process-local mirrors; Redis TTL remains transport SSOT."""
        resolved_now = now or datetime.now(UTC)
        cutoff = resolved_now - timedelta(seconds=self._chat_turn_ttl_seconds)
        expired: list[str] = []
        for run_id, record in self._chat_turns.items():
            try:
                updated_at = datetime.fromisoformat(record.updated_at)
            except (TypeError, ValueError):
                updated_at = resolved_now
            if updated_at < cutoff:
                expired.append(run_id)
        for run_id in expired:
            self._chat_turns.pop(run_id, None)

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
            self._prune_local_expired_locked()
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
            self._prune_local_expired_locked()
            return list(reversed(self._chat_turns.values()))

    async def list_pending_dispatches(
        self,
        *,
        limit: int = 100,
    ) -> list[ChatTurnRunRecord]:
        """Load the oldest durable broker intents for reconciliation."""
        capped_limit = max(1, min(500, int(limit)))
        if self._redis is not None:
            try:
                run_ids = await self._redis.zrange(
                    self._dispatch_index_key(),
                    0,
                    capped_limit - 1,
                )
            except Exception as exc:
                raise ChatTurnTransportUnavailableError(
                    "Chat turn dispatch index is unavailable"
                ) from exc
            await self._load_records_from_redis([str(item) for item in run_ids])
            return [
                self._chat_turns[str(run_id)]
                for run_id in run_ids
                if str(run_id) in self._chat_turns
                and self._chat_turns[str(run_id)].status
                == ChatTurnRunStatus.pending
                and self._chat_turns[str(run_id)].worker_task_id is None
            ]

        async with self._lock:
            self._prune_local_expired_locked()
            return [
                record
                for record in self._chat_turns.values()
                if record.status == ChatTurnRunStatus.pending
                and record.worker_task_id is None
            ][:capped_limit]

    async def transition_status(
        self,
        run_id: str,
        status: ChatTurnRunStatus,
        *,
        expected: Collection[ChatTurnRunStatus],
        error: str | None = None,
        expected_execution_owner: str | None = None,
    ) -> bool:
        """Conditionally move one run while serializing cross-process writers."""
        expected_statuses = frozenset(expected)
        if not expected_statuses:
            return False
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return False
        try:
            record = await self.get_or_load(run_id, refresh=self._redis is not None)
            if record is None:
                return False
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None or current.status not in expected_statuses:
                    return False
                if (
                    expected_execution_owner is not None
                    and current.execution_owner != expected_execution_owner
                ):
                    return False
                previous = (
                    current.status,
                    current.updated_at,
                    current.error,
                )
                current.status = status
                current.updated_at = _now_iso()
                if error is not None:
                    current.error = error
                snapshot = current
            if await self._persist_record(snapshot):
                return True
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is not None and current is snapshot:
                    current.status, current.updated_at, current.error = previous
            return False
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def claim_execution(
        self,
        run_id: str,
        *,
        wait_seconds: float | None = None,
    ) -> str | None:
        """Claim one transient worker execution, including stale running runs."""
        owner = uuid.uuid4().hex
        wait_for = (
            self._execution_lease_seconds + self._execution_claim_poll_seconds
            if wait_seconds is None
            else max(0.0, float(wait_seconds))
        )
        deadline = time.monotonic() + wait_for

        while True:
            lock_token = await self._acquire_run_state_lock(run_id)
            if self._redis is not None and lock_token is None:
                if time.monotonic() >= deadline:
                    return None
                await asyncio.sleep(self._execution_claim_poll_seconds)
                continue

            claimed = False
            previous: tuple[
                ChatTurnRunStatus,
                str | None,
                str | None,
                str,
            ] | None = None
            try:
                record = await self.get_or_load(
                    run_id,
                    refresh=self._redis is not None,
                )
                if record is None or record.status not in (
                    ChatTurnRunStatus.pending,
                    ChatTurnRunStatus.running,
                ):
                    return None

                now = datetime.now(UTC)
                async with self._lock:
                    current = self._chat_turns.get(run_id)
                    if current is None or current.status not in (
                        ChatTurnRunStatus.pending,
                        ChatTurnRunStatus.running,
                    ):
                        return None
                    active_owner = current.execution_owner
                    lease_expired = self._lease_is_expired(
                        current.execution_lease_until,
                        now=now,
                    )
                    if (
                        current.status == ChatTurnRunStatus.pending
                        or not active_owner
                        or lease_expired
                    ):
                        previous = (
                            current.status,
                            current.execution_owner,
                            current.execution_lease_until,
                            current.updated_at,
                        )
                        current.status = ChatTurnRunStatus.running
                        current.execution_owner = owner
                        current.execution_lease_until = (
                            now + timedelta(seconds=self._execution_lease_seconds)
                        ).isoformat()
                        current.updated_at = now.isoformat()
                        snapshot = current
                        claimed = True

                if claimed:
                    persisted = await self._persist_record(snapshot)
                    if persisted:
                        return owner
                    async with self._lock:
                        current = self._chat_turns.get(run_id)
                        if current is not None and current.execution_owner == owner:
                            assert previous is not None
                            (
                                current.status,
                                current.execution_owner,
                                current.execution_lease_until,
                                current.updated_at,
                            ) = previous
                    raise RuntimeError(
                        f"Failed to persist execution claim for chat turn {run_id}"
                    )
            finally:
                await self._release_run_state_lock(run_id, lock_token)

            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(self._execution_claim_poll_seconds)

    async def renew_execution_claim(
        self,
        run_id: str,
        owner: str,
    ) -> ChatTurnExecutionRenewal:
        """Extend a worker claim while its transient execution is alive."""
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return ChatTurnExecutionRenewal.retryable
        try:
            try:
                record = await self.get_or_load(
                    run_id,
                    refresh=self._redis is not None,
                )
            except ChatTurnTransportUnavailableError:
                return ChatTurnExecutionRenewal.retryable
            if record is None:
                return ChatTurnExecutionRenewal.retryable
            now = datetime.now(UTC)
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if (
                    current is None
                    or current.status != ChatTurnRunStatus.running
                    or current.execution_owner != owner
                ):
                    return ChatTurnExecutionRenewal.lost
                previous_lease_until = current.execution_lease_until
                previous_updated_at = current.updated_at
                current.execution_lease_until = (
                    now + timedelta(seconds=self._execution_lease_seconds)
                ).isoformat()
                current.updated_at = now.isoformat()
                snapshot = current
            if await self._persist_record(snapshot):
                return ChatTurnExecutionRenewal.renewed
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is not None and current.execution_owner == owner:
                    current.execution_lease_until = previous_lease_until
                    current.updated_at = previous_updated_at
            return ChatTurnExecutionRenewal.retryable
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def release_execution_claim(self, run_id: str, owner: str) -> None:
        """Release a worker claim without changing the run lifecycle status."""
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return
        try:
            record = await self.get_or_load(
                run_id,
                refresh=self._redis is not None,
            )
            if record is None:
                return
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None or current.execution_owner != owner:
                    return
                previous = (
                    current.execution_owner,
                    current.execution_lease_until,
                )
                current.execution_owner = None
                current.execution_lease_until = None
                snapshot = current
            if not await self._persist_record(snapshot):
                async with self._lock:
                    current = self._chat_turns.get(run_id)
                    if current is not None and current is snapshot:
                        (
                            current.execution_owner,
                            current.execution_lease_until,
                        ) = previous
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def claim_dispatch(
        self,
        run_id: str,
        *,
        wait_seconds: float | None = None,
    ) -> str | None:
        """Claim the broker-publication window for one pending transport."""
        owner = uuid.uuid4().hex
        wait_for = (
            self._dispatch_lease_seconds + self._dispatch_claim_poll_seconds
            if wait_seconds is None
            else max(0.0, float(wait_seconds))
        )
        deadline = time.monotonic() + wait_for
        while True:
            lock_token = await self._acquire_run_state_lock(run_id)
            if self._redis is not None and lock_token is None:
                if time.monotonic() >= deadline:
                    return None
                await asyncio.sleep(self._dispatch_claim_poll_seconds)
                continue
            try:
                record = await self.get_or_load(
                    run_id,
                    refresh=self._redis is not None,
                )
                if record is None:
                    return None
                now = datetime.now(UTC)
                async with self._lock:
                    current = self._chat_turns.get(run_id)
                    if (
                        current is None
                        or current.status != ChatTurnRunStatus.pending
                        or current.worker_task_id is not None
                    ):
                        return None
                    active_dispatch = current.dispatch_owner and not self._lease_is_expired(
                        current.dispatch_lease_until,
                        now=now,
                    )
                    if not active_dispatch:
                        previous = (
                            current.dispatch_owner,
                            current.dispatch_lease_until,
                            current.updated_at,
                        )
                        current.dispatch_owner = owner
                        current.dispatch_lease_until = (
                            now + timedelta(seconds=self._dispatch_lease_seconds)
                        ).isoformat()
                        current.updated_at = now.isoformat()
                        snapshot = current
                    else:
                        snapshot = None
                if snapshot is not None:
                    if await self._persist_record(snapshot):
                        return owner
                    async with self._lock:
                        current = self._chat_turns.get(run_id)
                        if current is not None and current.dispatch_owner == owner:
                            (
                                current.dispatch_owner,
                                current.dispatch_lease_until,
                                current.updated_at,
                            ) = previous
            finally:
                await self._release_run_state_lock(run_id, lock_token)
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(self._dispatch_claim_poll_seconds)

    async def mark_dispatched(
        self,
        run_id: str,
        *,
        owner: str,
        worker_task_id: str,
    ) -> bool:
        """Fence and record successful broker publication."""
        normalized_task_id = str(worker_task_id).strip()
        if not normalized_task_id:
            raise ValueError("worker_task_id must not be empty")
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return False
        try:
            record = await self.get_or_load(run_id, refresh=self._redis is not None)
            if record is None:
                return False
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None or current.dispatch_owner != owner:
                    return False
                current.worker_task_id = normalized_task_id
                current.dispatch_owner = None
                current.dispatch_lease_until = None
                current.updated_at = _now_iso()
                snapshot = current
            return await self._persist_record(snapshot)
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def release_dispatch_claim(self, run_id: str, *, owner: str) -> None:
        """Release an unconfirmed broker-publication claim for retry."""
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return
        try:
            record = await self.get_or_load(run_id, refresh=self._redis is not None)
            if record is None:
                return
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None or current.dispatch_owner != owner:
                    return
                previous = (
                    current.dispatch_owner,
                    current.dispatch_lease_until,
                    current.updated_at,
                )
                current.dispatch_owner = None
                current.dispatch_lease_until = None
                current.updated_at = _now_iso()
                snapshot = current
            if not await self._persist_record(snapshot):
                async with self._lock:
                    current = self._chat_turns.get(run_id)
                    if current is not None and current is snapshot:
                        (
                            current.dispatch_owner,
                            current.dispatch_lease_until,
                            current.updated_at,
                        ) = previous
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def bind_thread(
        self,
        run_id: str,
        thread_id: str,
        *,
        expected_execution_owner: str | None = None,
    ) -> bool:
        """Bind a run to its resolved thread once preparation finishes."""
        normalized = str(thread_id).strip()
        if not normalized:
            return False
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return False
        try:
            record = await self.get_or_load(run_id, refresh=self._redis is not None)
            if record is None:
                return False
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None:
                    return False
                if (
                    expected_execution_owner is not None
                    and current.execution_owner != expected_execution_owner
                ):
                    return False
                previous_thread_id = current.thread_id
                previous_updated_at = current.updated_at
                current.thread_id = normalized
                current.updated_at = _now_iso()
                snapshot = current
            if await self._persist_record(
                snapshot,
                previous_thread_id=previous_thread_id,
            ):
                return True
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is not None and current is snapshot:
                    current.thread_id = previous_thread_id
                    current.updated_at = previous_updated_at
            return False
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def create_or_reject(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: ChatTurnDisconnectMode = ChatTurnDisconnectMode.cancel,
        metadata: dict[str, Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        multitask_strategy: str = "reject",
        request_idempotency_key: str | None = None,
        request_fingerprint: str | None = None,
        dispatch_payload: Mapping[str, Any] | None = None,
    ) -> ChatTurnRunAdmission:
        run_id = str(uuid.uuid4())
        now = _now_iso()
        supported = ("reject", "interrupt", "rollback")
        normalized_thread_id = str(thread_id).strip() or run_id
        normalized_request_key = str(request_idempotency_key or "").strip()
        normalized_fingerprint = str(request_fingerprint or "").strip()
        if bool(normalized_request_key) != bool(normalized_fingerprint):
            raise ValueError(
                "request idempotency key and fingerprint must be supplied together"
            )
        request_lock_token = (
            await self._acquire_request_scheduling_lock(normalized_request_key)
            if normalized_request_key
            else None
        )
        local_scheduling_acquired = False
        if self._redis is None:
            await self._local_scheduling_lock.acquire()
            local_scheduling_acquired = True
        if (
            self._redis is not None
            and normalized_request_key
            and request_lock_token is None
        ):
            raise ChatTurnTransportUnavailableError(
                "Chat request scheduling state is unavailable"
            )
        lock_token: str | None = None
        try:
            lock_token = await self._acquire_thread_scheduling_lock(
                normalized_thread_id
            )
            if self._redis is not None and lock_token is None:
                raise ChatTurnTransportUnavailableError(
                    f"Thread {normalized_thread_id} scheduling state is unavailable"
                )
            # In distributed mode, ensure local memory sees recent thread runs
            # before applying multitask_strategy decisions.
            await self._load_thread_chat_turns_from_redis(normalized_thread_id)

            if multitask_strategy not in supported:
                raise UnsupportedChatTurnStrategyError(
                    f"Multitask strategy '{multitask_strategy}' is not supported. "
                    f"Supported strategies: {', '.join(supported)}"
                )
            if normalized_request_key:
                if self._redis is not None:
                    try:
                        indexed_run_id = await self._redis.get(
                            self._request_index_key(normalized_request_key)
                        )
                    except Exception as exc:
                        raise ChatTurnTransportUnavailableError(
                            "Chat request index is unavailable"
                        ) from exc
                    if indexed_run_id:
                        await self._load_record_from_redis(str(indexed_run_id))
                async with self._lock:
                    self._prune_local_expired_locked()
                    replay = next(
                        (
                            item
                            for item in self._chat_turns.values()
                            if item.metadata.get(_REQUEST_KEY_METADATA)
                            == normalized_request_key
                        ),
                        None,
                    )
                if replay is not None:
                    if (
                        replay.metadata.get(_REQUEST_FINGERPRINT_METADATA)
                        != normalized_fingerprint
                    ):
                        raise ChatTurnConflictError(
                            "Chat request_id was reused for a different payload"
                        )
                    return ChatTurnRunAdmission(record=replay, created=False)
            if self._redis is not None and multitask_strategy in (
                "interrupt",
                "rollback",
            ):
                async with self._lock:
                    inflight_ids = [
                        item.run_id
                        for item in self._chat_turns.values()
                        if item.thread_id == normalized_thread_id
                        and item.status
                        in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running)
                    ]
                for inflight_id in inflight_ids:
                    await self.cancel(inflight_id, action=multitask_strategy)

            persisted_updates: list[ChatTurnRunRecord] = []
            async with self._lock:
                self._prune_local_expired_locked()
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

                run_metadata = dict(metadata or {})
                if normalized_request_key:
                    run_metadata[_REQUEST_KEY_METADATA] = normalized_request_key
                    run_metadata[_REQUEST_FINGERPRINT_METADATA] = (
                        normalized_fingerprint
                    )
                created = ChatTurnRunRecord(
                    run_id=run_id,
                    thread_id=normalized_thread_id,
                    assistant_id=assistant_id,
                    status=ChatTurnRunStatus.pending,
                    on_disconnect=on_disconnect,
                    multitask_strategy=multitask_strategy,
                    metadata=run_metadata,
                    kwargs=kwargs or {},
                    dispatch_payload=dict(dispatch_payload or {}),
                    created_at=now,
                    updated_at=now,
                )
                self._chat_turns[run_id] = created
                persisted_updates.append(created)

            for record in persisted_updates:
                if not await self._persist_record(record):
                    async with self._lock:
                        for item in persisted_updates:
                            self._chat_turns.pop(item.run_id, None)
                    raise ChatTurnTransportUnavailableError(
                        "Chat turn admission could not be persisted"
                    )

            logger.info(
                "Run created: run_id=%s thread_id=%s",
                created.run_id,
                created.thread_id,
            )
            return ChatTurnRunAdmission(record=created, created=True)
        finally:
            await self._release_thread_scheduling_lock(normalized_thread_id, lock_token)
            if normalized_request_key:
                await self._release_request_scheduling_lock(
                    normalized_request_key,
                    request_lock_token,
                )
            if local_scheduling_acquired:
                self._local_scheduling_lock.release()

    async def cancel(self, run_id: str, *, action: str = "interrupt") -> bool:
        lock_token = await self._acquire_run_state_lock(run_id)
        if self._redis is not None and lock_token is None:
            return False
        try:
            record = await self.get_or_load(run_id, refresh=self._redis is not None)
            if record is None:
                return False
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is None or current.status not in (
                    ChatTurnRunStatus.pending,
                    ChatTurnRunStatus.running,
                ):
                    return False
                previous = (
                    current.abort_action,
                    current.status,
                    current.updated_at,
                    current.abort_event.is_set(),
                )
                current.abort_action = action
                current.abort_event.set()
                if current.task is not None and not current.task.done():
                    current.task.cancel()
                current.status = ChatTurnRunStatus.interrupted
                current.updated_at = _now_iso()
                snapshot = current
            if await self._persist_record(snapshot):
                return True
            async with self._lock:
                current = self._chat_turns.get(run_id)
                if current is not None and current is snapshot:
                    (
                        current.abort_action,
                        current.status,
                        current.updated_at,
                        abort_was_set,
                    ) = previous
                    if not abort_was_set:
                        current.abort_event.clear()
            return False
        finally:
            await self._release_run_state_lock(run_id, lock_token)

    async def wait_for_abort(
        self,
        run_id: str,
        *,
        poll_interval: float = 0.1,
    ) -> str:
        """Wait for a local or cross-process abort request and return its action."""
        interval = max(0.02, float(poll_interval))
        while True:
            try:
                record = await self.get_or_load(
                    run_id,
                    refresh=self._redis is not None,
                )
            except ChatTurnTransportUnavailableError:
                await asyncio.sleep(interval)
                continue
            if record is None:
                await asyncio.sleep(interval)
                continue
            if record.abort_event.is_set() or record.status == ChatTurnRunStatus.interrupted:
                record.abort_event.set()
                return str(record.abort_action or "interrupt")
            try:
                await asyncio.wait_for(record.abort_event.wait(), timeout=interval)
            except TimeoutError:
                continue

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

    async def delete(self, run_id: str) -> bool:
        """Delete one terminal transient transport and all of its indices."""
        record = await self.get_or_load(run_id, refresh=self._redis is not None)
        if record is None:
            return False
        if record.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running):
            raise ChatTurnConflictError("Active chat turn must be cancelled before deletion")
        thread_id = record.thread_id
        request_key = str(
            record.metadata.get(_REQUEST_KEY_METADATA) or ""
        ).strip()
        async with self._lock:
            self._chat_turns.pop(run_id, None)
        await self._delete_record_from_redis(
            run_id,
            thread_id=thread_id,
            request_key=request_key or None,
        )
        return True
