"""Persistence helpers for durable subagent lifecycle records."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import SubagentTaskRecord
from src.services.thread_billing import extract_persisted_metadata_usage
from src.subagents.models import SubagentResult, SubagentTask

_TERMINAL_SUBAGENT_STATUSES = {"completed", "failed", "cancelled", "timed_out"}


def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


class SubagentTaskStore:
    """Read/write durable subagent task records."""

    def __init__(
        self,
        db_session: AsyncSession,
        model: type[SubagentTaskRecord] = SubagentTaskRecord,
    ) -> None:
        self._db = db_session
        self._model = model

    async def get_task_record(self, task_id: str) -> SubagentTaskRecord | None:
        result = await self._db.execute(
            select(self._model).where(self._model.id == task_id)
        )
        return result.scalar_one_or_none()

    async def upsert_task_record(
        self,
        *,
        task: SubagentTask,
        status: str,
        result: SubagentResult | None = None,
        occurred_at: datetime | None = None,
    ) -> SubagentTaskRecord:
        """Create or update the durable state for a subagent task."""
        now = occurred_at or datetime.now(UTC)
        record = await self.get_task_record(task.task_id)
        subagent_type = task.metadata.get("subagent_type")
        task_metadata = (
            dict(task.metadata)
            if isinstance(task.metadata, dict)
            else {}
        )
        result_metadata = (
            dict(result.metadata)
            if result is not None and isinstance(result.metadata, dict)
            else {}
        )
        usage = extract_persisted_metadata_usage(result_metadata)
        if usage is None:
            usage = extract_persisted_metadata_usage(task_metadata)
        if usage is not None:
            task_metadata["token_usage"] = usage.as_dict()
        model_name = result_metadata.get("model_name")
        if model_name is None:
            model_name = task_metadata.get("model_name")
        if isinstance(model_name, str) and model_name.strip():
            task_metadata["model_name"] = model_name.strip()
        if result is not None:
            task_metadata["turns_used"] = max(int(result.turns_used or 0), 0)
            try:
                task_metadata["duration_seconds"] = max(float(result.duration_seconds), 0.0)
            except (TypeError, ValueError):
                task_metadata["duration_seconds"] = 0.0
        execution_session_id = str(
            task_metadata.get("execution_session_id") or ""
        ).strip()
        if not execution_session_id:
            raise ValueError("execution_session_id is required for subagent task persistence")
        output_preview = _truncate_preview(result.output if result else None)
        error = result.error if result else None

        if record is None:
            record = self._model(
                id=task.task_id,
                user_id=(
                    str(task.metadata.get("user_id"))
                    if task.metadata.get("user_id") is not None
                    else None
                ),
                workspace_id=(
                    str(task.metadata.get("workspace_id"))
                    if task.metadata.get("workspace_id") is not None
                    else None
                ),
                execution_session_id=(
                    execution_session_id
                ),
                thread_id=task.thread_id,
                subagent_type=str(subagent_type) if subagent_type is not None else None,
                status=status,
                prompt=task.prompt,
                output_preview=output_preview,
                error=error,
                task_metadata=task_metadata,
                created_at=task.created_at or now,
                updated_at=now,
                completed_at=now if status in _TERMINAL_SUBAGENT_STATUSES else None,
            )
            self._db.add(record)
        else:
            record.status = status
            record.prompt = task.prompt
            record.execution_session_id = (
                execution_session_id
            )
            record.subagent_type = str(subagent_type) if subagent_type is not None else None
            record.output_preview = output_preview
            record.error = error
            record.task_metadata = task_metadata
            record.updated_at = now
            record.completed_at = now if status in _TERMINAL_SUBAGENT_STATUSES else None

        await self._db.commit()
        await self._db.refresh(record)
        return record

    async def list_workspace_records(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[SubagentTaskRecord]:
        result = await self._db.execute(
            select(self._model)
            .where(self._model.workspace_id == workspace_id)
            .order_by(
                func.coalesce(
                    self._model.completed_at,
                    self._model.updated_at,
                    self._model.created_at,
                ).desc()
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_thread_records(
        self,
        thread_id: str,
        *,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[SubagentTaskRecord]:
        query = select(self._model).where(self._model.thread_id == thread_id)
        if user_id:
            query = query.where(self._model.user_id == user_id)
        result = await self._db.execute(
            query.order_by(self._model.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
