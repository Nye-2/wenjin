"""Task storage layer - Redis for runtime, PostgreSQL for persistence."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.task_config import task_settings
from src.database.models.task import TaskRecord
from src.task.registry import TaskStatus
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task state in Redis and PostgreSQL."""

    def __init__(self, redis_client, db_session: AsyncSession):
        self._redis = redis_client
        self._db = db_session

    def _record_model(self):
        """Return the SQLAlchemy model used for task persistence."""
        return getattr(self, "_model", getattr(self, "_test_model", TaskRecord))

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
        metadata: dict | None = None,
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

    async def get_task_state(self, task_id: str) -> dict | None:
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
        payload: dict,
    ) -> TaskRecord:
        """Create a new task record in PostgreSQL."""
        record_model = self._record_model()
        record = record_model(
            id=task_id,
            user_id=user_id,
            task_type=task_type,
            status="pending",
            priority=priority,
            payload=payload,
        )
        self._db.add(record)
        await self._db.commit()
        await self._db.refresh(record)
        return record

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
        **updates,
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
    ) -> list[TaskRecord]:
        """List tasks for a user."""
        record_model = self._record_model()
        query = select(record_model).where(record_model.user_id == user_id)

        if status:
            query = query.where(record_model.status == status)
        if task_type:
            query = query.where(record_model.task_type == task_type)

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
        await self.update_task_record(
            task_id,
            status=TaskStatus.RUNNING.value,
            started_at=datetime.now(UTC),
        )
        await self.set_task_state(task_id, TaskStatus.RUNNING.value, worker_id=worker_id)

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Mark task as completed (success or failed)."""
        status = TaskStatus.SUCCESS.value if success else TaskStatus.FAILED.value
        runtime_state = await self.get_task_state(task_id)
        final_progress = 100 if success else runtime_state.get("progress", 0) if runtime_state else 0
        final_message = error or runtime_state.get("message") if runtime_state else error
        record = await self.update_task_record(
            task_id,
            status=status,
            result=result,
            error=error,
            completed_at=datetime.now(UTC),
            progress=final_progress,
            message=final_message,
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
                },
            )

            refresh_targets = ["activity", "dashboard"]
            if success and isinstance(result, dict):
                for target in result.get("refresh_targets") or []:
                    if isinstance(target, str) and target not in refresh_targets:
                        refresh_targets.append(target)
            await publish_workspace_event(
                workspace_id,
                "workspace.refresh",
                {"refresh_targets": refresh_targets},
            )
