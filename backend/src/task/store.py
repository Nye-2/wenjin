"""Task storage layer - Redis for runtime, PostgreSQL for persistence."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func as sa_func
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.task_config import task_settings
from src.database.models.task import TaskRecord
from src.services.workspace_activity_contracts import (
    build_task_activity_item,
    serialize_activity_item,
)
from src.task.registry import TaskStatus
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task state in Redis and PostgreSQL."""

    def __init__(self, redis_client: Any, db_session: AsyncSession) -> None:
        self._redis = redis_client
        self._db = db_session

    def _record_model(self) -> type[TaskRecord]:
        """Return the SQLAlchemy model used for task persistence."""
        return cast(type[TaskRecord], getattr(self, "_model", getattr(self, "_test_model", TaskRecord)))

    @staticmethod
    def _advisory_lock_key(user_id: str) -> int:
        """Derive a stable signed bigint lock key for per-user task submission."""
        digest = hashlib.blake2b(user_id.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    # === Redis Operations (Runtime State) ===

    def _task_key(self, task_id: str) -> str:
        """Redis key for task state."""
        return f"task:{task_id}"

    async def set_task_state(
        self,
        task_id: str,
        status: str,
        progress: int = 0,
        message: str | None = None,
        current_step: str | None = None,
        worker_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set task state in Redis."""
        key = self._task_key(task_id)
        data = {
            "status": status,
            "progress": str(progress),
            "message": message or "",
            "current_step": current_step or "",
            "worker_id": worker_id or "",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if metadata is not None:
            data["metadata"] = json.dumps(metadata, ensure_ascii=False)
        await self._redis.client.hset(key, mapping=data)
        await self._redis.client.expire(key, task_settings.task_redis_ttl)

    async def get_task_state(self, task_id: str) -> dict[str, Any] | None:
        """Get task state from Redis."""
        key = self._task_key(task_id)
        data = await self._redis.client.hgetall(key)
        if not data:
            return None
        raw_metadata = data.get("metadata", "")
        metadata = None
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                logger.warning("Failed to decode task metadata for task %s", task_id)
        return {
            "status": data.get("status", "unknown"),
            "progress": int(data.get("progress", 0)),
            "message": data.get("message", ""),
            "current_step": data.get("current_step", ""),
            "worker_id": data.get("worker_id", ""),
            "updated_at": data.get("updated_at", ""),
            "metadata": metadata,
        }

    async def delete_task_state(self, task_id: str) -> None:
        """Delete task state from Redis."""
        key = self._task_key(task_id)
        await self._redis.client.delete(key)

    # === PostgreSQL Operations (Persistence) ===

    async def create_task_record(
        self,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict[str, Any],
    ) -> TaskRecord:
        """Create a new task record in PostgreSQL."""
        record_model = self._record_model()
        _payload = payload or {}
        _params = _payload.get("params", {}) if isinstance(_payload, dict) else {}
        record = record_model(
            id=task_id,
            user_id=user_id,
            task_type=task_type,
            status="pending",
            priority=priority,
            payload=payload,
            workspace_id=_payload.get("workspace_id") or _params.get("workspace_id"),
            feature_id=_payload.get("feature_id"),
            thread_id=_payload.get("thread_id"),
            action=_payload.get("action") or _params.get("action"),
        )
        self._db.add(record)
        await self._db.commit()
        await self._db.refresh(record)
        return record

    async def create_task_record_guarded(
        self,
        *,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict[str, Any],
        concurrency_limit: int,
    ) -> tuple[TaskRecord | None, int]:
        """Atomically enforce per-user active-task limit and create the task record."""
        record_model = self._record_model()
        active_statuses = [
            TaskStatus.PENDING.value,
            TaskStatus.RUNNING.value,
        ]

        tx = self._db.begin_nested() if self._db.in_transaction() else self._db.begin()
        async with tx:
            bind = self._db.get_bind()
            if bind is not None and bind.dialect.name == "postgresql":
                await self._db.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": self._advisory_lock_key(user_id)},
                )

            count_result = await self._db.execute(
                select(sa_func.count())
                .select_from(record_model)
                .where(
                    record_model.user_id == user_id,
                    record_model.status.in_(active_statuses),
                )
            )
            active_count = count_result.scalar() or 0
            if active_count >= concurrency_limit:
                return None, active_count

            _payload = payload or {}
            _params = _payload.get("params", {}) if isinstance(_payload, dict) else {}
            record = record_model(
                id=task_id,
                user_id=user_id,
                task_type=task_type,
                status=TaskStatus.PENDING.value,
                priority=priority,
                payload=payload,
                workspace_id=_payload.get("workspace_id") or _params.get("workspace_id"),
                feature_id=_payload.get("feature_id"),
                thread_id=_payload.get("thread_id"),
                action=_payload.get("action") or _params.get("action"),
            )
            self._db.add(record)
            await self._db.flush()

        await self._db.refresh(record)
        return record, active_count

    async def get_task_record(self, task_id: str) -> TaskRecord | None:
        """Get task record from PostgreSQL."""
        record_model = self._record_model()
        result = await self._db.execute(
            select(record_model).where(record_model.id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_task_record(
        self,
        task_id: str,
        **updates: Any,
    ) -> TaskRecord | None:
        """Update task record in PostgreSQL."""
        record = await self.get_task_record(task_id)
        if not record:
            return None

        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)

        await self._db.commit()
        await self._db.refresh(record)
        return record

    async def list_user_tasks(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
        feature_id: str | None = None,
    ) -> list[TaskRecord]:
        """List tasks for a user."""
        record_model = self._record_model()
        query = select(record_model).where(record_model.user_id == user_id)

        if status:
            query = query.where(record_model.status == status)
        if task_type:
            query = query.where(record_model.task_type == task_type)
        if workspace_id is not None:
            query = query.where(record_model.workspace_id == workspace_id)
        if feature_id is not None:
            query = query.where(record_model.feature_id == feature_id)

        query = query.order_by(record_model.created_at.desc()).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def count_active_tasks(self, user_id: str) -> int:
        """Count active (pending/running) tasks for a user."""
        record_model = self._record_model()
        active_statuses = [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]
        query = (
            select(sa_func.count())
            .select_from(record_model)
            .where(
                record_model.user_id == user_id,
                record_model.status.in_(active_statuses),
            )
        )
        result = await self._db.execute(query)
        return result.scalar() or 0

    async def mark_task_started(self, task_id: str, worker_id: str | None = None) -> None:
        """Mark task as started."""
        started_at = datetime.now(UTC)
        record = await self.update_task_record(
            task_id,
            status=TaskStatus.RUNNING.value,
            started_at=started_at,
        )
        await self.set_task_state(task_id, TaskStatus.RUNNING.value, worker_id=worker_id)
        payload = record.payload if record and isinstance(record.payload, dict) else {}
        workspace_id = str(payload.get("workspace_id")) if payload.get("workspace_id") else None
        if workspace_id:
            await publish_workspace_event(
                workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": task_id,
                        "task_type": record.task_type if record else None,
                        "status": TaskStatus.RUNNING.value,
                        "progress": record.progress if record else 0,
                        "message": record.message if record else None,
                        "feature_id": payload.get("feature_id"),
                        "thread_id": payload.get("thread_id"),
                        "metadata": None,
                    },
                    "activity": serialize_activity_item(
                        build_task_activity_item(
                            task_id=task_id,
                            workspace_id=workspace_id,
                            task_type=record.task_type if record else None,
                            payload=payload if isinstance(payload, dict) else None,
                            status=TaskStatus.RUNNING.value,
                            progress=record.progress if record else 0,
                            message=record.message if record else None,
                            error=None,
                            occurred_at=started_at,
                            created_at=record.created_at if record else None,
                            started_at=started_at,
                        )
                    ),
                },
            )

    async def persist_runtime_state(self, task_id: str, metadata: dict[str, Any] | None) -> None:
        """Persist task runtime metadata to PostgreSQL for refresh/reconnect recovery."""
        runtime_state: dict[str, Any] | None = None
        if isinstance(metadata, dict):
            runtime_candidate = metadata.get("runtime")
            if isinstance(runtime_candidate, dict):
                runtime_state = runtime_candidate
        await self.update_task_record(task_id, runtime_state=runtime_state)

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark task as completed (success or failed)."""
        status = TaskStatus.SUCCESS.value if success else TaskStatus.FAILED.value
        runtime_state = await self.get_task_state(task_id)
        final_progress = 100 if success else runtime_state.get("progress", 0) if runtime_state else 0
        final_message = error or runtime_state.get("message") if runtime_state else error
        completed_at = datetime.now(UTC)
        record = await self.update_task_record(
            task_id,
            status=status,
            result=result,
            error=error,
            completed_at=completed_at,
            progress=final_progress,
            message=final_message,
            runtime_state=(
                runtime_state.get("metadata", {}).get("runtime")
                if runtime_state and isinstance(runtime_state.get("metadata"), dict)
                else None
            ),
        )
        # Keep Redis state for a while for queries
        await self.set_task_state(
            task_id,
            status,
            progress=final_progress,
            message=final_message,
            metadata=runtime_state.get("metadata") if runtime_state else None,
        )

        payload = record.payload if record and isinstance(record.payload, dict) else {}
        workspace_id = str(payload.get("workspace_id")) if payload.get("workspace_id") else None
        if workspace_id:
            await publish_workspace_event(
                workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": task_id,
                        "task_type": record.task_type if record else None,
                        "status": status,
                        "progress": final_progress,
                        "message": final_message,
                        "feature_id": payload.get("feature_id"),
                        "thread_id": payload.get("thread_id"),
                        "metadata": runtime_state.get("metadata") if runtime_state else None,
                        "result": result,
                        "error": error,
                    }
                }
                | {
                    "activity": serialize_activity_item(
                        build_task_activity_item(
                            task_id=task_id,
                            workspace_id=workspace_id,
                            task_type=record.task_type if record else None,
                            payload=payload if isinstance(payload, dict) else None,
                            status=status,
                            progress=final_progress,
                            message=final_message,
                            error=error,
                            result=result if isinstance(result, dict) else result,
                            occurred_at=completed_at,
                            created_at=record.created_at if record else None,
                            started_at=record.started_at if record else None,
                            completed_at=completed_at,
                        )
                    )
                },
            )

            refresh_targets = ["dashboard"]
            if success and isinstance(result, dict):
                for target in result.get("refresh_targets") or []:
                    if isinstance(target, str) and target not in refresh_targets:
                        refresh_targets.append(target)
            await publish_workspace_event(
                workspace_id,
                "workspace.refresh",
                {"refresh_targets": refresh_targets},
            )
