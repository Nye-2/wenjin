"""Task storage layer - Redis for runtime, PostgreSQL for persistence."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.task_config import task_settings
from src.database.models.task import TaskRecord

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task state in Redis and PostgreSQL."""

    def __init__(self, redis_client, db_session: AsyncSession):
        self._redis = redis_client
        self._db = db_session

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
    ) -> None:
        """Set task state in Redis."""
        key = self._task_key(task_id)
        data = {
            "status": status,
            "progress": str(progress),
            "message": message or "",
            "current_step": current_step or "",
            "worker_id": worker_id or "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.client.hset(key, mapping=data)
        await self._redis.client.expire(key, task_settings.task_redis_ttl)

    async def get_task_state(self, task_id: str) -> dict | None:
        """Get task state from Redis."""
        key = self._task_key(task_id)
        data = await self._redis.client.hgetall(key)
        if not data:
            return None
        return {
            "status": data.get("status", "unknown"),
            "progress": int(data.get("progress", 0)),
            "message": data.get("message", ""),
            "current_step": data.get("current_step", ""),
            "worker_id": data.get("worker_id", ""),
            "updated_at": data.get("updated_at", ""),
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
        record = TaskRecord(
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
        result = await self._db.execute(
            select(TaskRecord).where(TaskRecord.id == task_id)
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
        query = select(TaskRecord).where(TaskRecord.user_id == user_id)

        if status:
            query = query.where(TaskRecord.status == status)
        if task_type:
            query = query.where(TaskRecord.task_type == task_type)

        query = query.order_by(TaskRecord.created_at.desc()).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def mark_task_started(self, task_id: str, worker_id: str | None = None) -> None:
        """Mark task as started."""
        await self.update_task_record(
            task_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        await self.set_task_state(task_id, "running", worker_id=worker_id)

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Mark task as completed (success or failed)."""
        status = "success" if success else "failed"
        await self.update_task_record(
            task_id,
            status=status,
            result=result,
            error=error,
            completed_at=datetime.now(timezone.utc),
            progress=100 if success else None,
        )
        # Keep Redis state for a while for queries
        await self.set_task_state(task_id, status, progress=100 if success else 0, message=error)
