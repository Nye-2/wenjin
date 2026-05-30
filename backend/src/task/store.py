"""Task storage layer - Redis for runtime, PostgreSQL for persistence."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from src.config.task_config import task_settings
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.task import (
    TaskRecordCompletedPayload,
    TaskRecordCreateGuardedPayload,
    TaskRecordCreatePayload,
    TaskRecordPatchPayload,
    TaskRecordPayload,
    TaskRecordRuntimeStatePayload,
    TaskRecordStartedPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.runtime.serialization import dumps_json
from src.services.execution_service import ExecutionService
from src.services.workspace_activity_contracts import (
    build_task_activity_item,
    build_task_result_next_actions,
    serialize_activity_item,
)
from src.task.registry import TaskStatus
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task state in Redis and PostgreSQL."""

    def __init__(
        self,
        redis_client: Any,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._redis = redis_client
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

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
            data["metadata"] = dumps_json(metadata, ensure_ascii=False)
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
    ) -> TaskRecordPayload:
        """Create a new task record in PostgreSQL."""
        async with self._client() as client:
            return await client.create_task_record(
                TaskRecordCreatePayload(
                    task_id=task_id,
                    user_id=user_id,
                    task_type=task_type,
                    priority=priority,
                    payload=payload,
                )
            )

    async def create_task_record_guarded(
        self,
        *,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict[str, Any],
        concurrency_limit: int,
    ) -> tuple[TaskRecordPayload | None, int]:
        """Atomically enforce per-user active-task limit and create the task record."""
        active_statuses = [
            TaskStatus.PENDING.value,
            TaskStatus.RUNNING.value,
        ]
        async with self._client() as client:
            return await client.create_task_record_guarded(
                TaskRecordCreateGuardedPayload(
                    task_id=task_id,
                    user_id=user_id,
                    task_type=task_type,
                    priority=priority,
                    payload=payload,
                    concurrency_limit=concurrency_limit,
                    active_statuses=active_statuses,
                )
            )

    async def get_task_record(self, task_id: str) -> TaskRecordPayload | None:
        """Get task record from PostgreSQL."""
        async with self._client() as client:
            return await client.get_task_record(task_id)

    async def update_task_record(
        self,
        task_id: str,
        *,
        commit: bool = True,
        **updates: Any,
    ) -> TaskRecordPayload | None:
        """Update task record in PostgreSQL."""
        _ = commit
        async with self._client() as client:
            return await client.update_task_record(
                task_id,
                TaskRecordPatchPayload(**updates),
            )

    async def list_user_tasks(
        self,
        user_id: str,
        status: str | list[str] | tuple[str, ...] | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
        feature_id: str | None = None,
        action: str | None = None,
    ) -> list[TaskRecordPayload]:
        """List tasks for a user."""
        async with self._client() as client:
            return await client.list_user_task_records(
                user_id=user_id,
                status=list(status) if isinstance(status, tuple) else status,
                task_type=task_type,
                limit=limit,
                workspace_id=workspace_id,
                feature_id=feature_id,
                action=action,
            )

    async def count_active_tasks(self, user_id: str) -> int:
        """Count active (pending/running) tasks for a user."""
        active_statuses = [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]
        async with self._client() as client:
            return await client.count_active_task_records(
                user_id=user_id,
                active_statuses=active_statuses,
            )

    async def mark_task_started(self, task_id: str, worker_id: str | None = None) -> None:
        """Mark task as started.

        DataService owns the task record; execution lifecycle is mirrored through
        ``ExecutionService`` using the same DataService client when available.
        """
        started_at = datetime.now(UTC)
        async with self._client() as client:
            record = await client.mark_task_record_started(
                task_id,
                TaskRecordStartedPayload(started_at=started_at),
            )
            if record and record.execution_id:
                await ExecutionService(
                    dataservice=client,
                ).apply_task_transition(
                    record.execution_id,
                    commit=False,
                    status=TaskStatus.RUNNING.value,
                    started_at=started_at,
                    next_actions=[],
                    advisory_code=None,
                    last_error=None,
                )
        if not record:
            return

        # Redis runtime cache (always derived from committed DB state)
        await self.set_task_state(task_id, TaskStatus.RUNNING.value, worker_id=worker_id)

        # Post-commit: touch compute projection
        if record.execution_id:
            from src.compute.session_service import ComputeSessionService

            await ComputeSessionService().touch_session_by_execution(
                record.execution_id
            )

        payload = record.payload if isinstance(record.payload, dict) else {}
        workspace_id = str(payload.get("workspace_id")) if payload.get("workspace_id") else None
        if workspace_id:
            await publish_workspace_event(
                workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": task_id,
                        "execution_id": record.execution_id,
                        "task_type": record.task_type,
                        "status": TaskStatus.RUNNING.value,
                        "progress": record.progress,
                        "message": record.message,
                        "feature_id": payload.get("feature_id"),
                        "thread_id": payload.get("thread_id"),
                        "metadata": None,
                    },
                    "activity": serialize_activity_item(
                        build_task_activity_item(
                            task_id=task_id,
                            workspace_id=workspace_id,
                            task_type=record.task_type,
                            payload=payload,
                            status=TaskStatus.RUNNING.value,
                            progress=record.progress,
                            message=record.message,
                            error=None,
                            occurred_at=started_at,
                            created_at=record.created_at,
                            started_at=started_at,
                        )
                    ),
                },
            )

    async def persist_runtime_state(self, task_id: str, metadata: dict[str, Any] | None) -> None:
        """Persist task runtime metadata to PostgreSQL for refresh/reconnect recovery.

        Runtime state is carried by the execution stream for canonical executions.
        """
        runtime_state: dict[str, Any] | None = None
        if isinstance(metadata, dict):
            runtime_candidate = metadata.get("runtime")
            if isinstance(runtime_candidate, dict):
                runtime_state = runtime_candidate

        async with self._client() as client:
            record = await client.persist_task_record_runtime_state(
                task_id,
                TaskRecordRuntimeStatePayload(runtime_state=runtime_state),
            )
            if record and record.execution_id and runtime_state is not None:
                await ExecutionService(
                    dataservice=client,
                ).apply_task_transition(
                    record.execution_id,
                    commit=False,
                    status=record.status,
                    runtime_state=runtime_state,
                    started_at=record.started_at,
                )
        if not record:
            return

        # Post-commit: touch compute projection and broadcast task.updated.
        if record.execution_id and runtime_state is not None:
            from src.compute.session_service import ComputeSessionService

            await ComputeSessionService().touch_session_by_execution(
                record.execution_id
            )

        payload = record.payload if isinstance(record.payload, dict) else {}
        workspace_id = str(payload.get("workspace_id")) if payload.get("workspace_id") else None
        if workspace_id:
            await publish_workspace_event(
                workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": task_id,
                        "execution_id": record.execution_id,
                        "task_type": record.task_type,
                        "status": record.status,
                        "progress": record.progress,
                        "message": record.message,
                        "feature_id": payload.get("feature_id"),
                        "thread_id": payload.get("thread_id"),
                        "metadata": runtime_state,
                    }
                },
            )

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark task as completed (success or failed).

        Completion is mirrored into the canonical execution record.
        """
        record = await self.get_task_record(task_id)
        if not record:
            return

        status = TaskStatus.SUCCESS.value if success else TaskStatus.FAILED.value
        runtime_state = await self.get_task_state(task_id)
        final_progress = 100 if success else runtime_state.get("progress", 0) if runtime_state else 0
        final_message = error or runtime_state.get("message") if runtime_state else error
        completed_at = datetime.now(UTC)

        # Derive result_summary, artifact_ids, next_actions before the tx
        result_summary = final_message if isinstance(final_message, str) and final_message else None
        artifact_ids: list[str] = []
        payload = record.payload if isinstance(record.payload, dict) else {}
        next_actions = build_task_result_next_actions(
            payload=payload,
            result=result if isinstance(result, dict) else None,
        )
        if isinstance(result, dict):
            raw_artifact_ids = result.get("artifact_ids")
            if isinstance(raw_artifact_ids, list):
                artifact_ids = [str(item) for item in raw_artifact_ids if str(item).strip()]
            if result_summary is None:
                raw_summary = result.get("summary")
                if isinstance(raw_summary, str) and raw_summary.strip():
                    result_summary = raw_summary.strip()

        runtime_snapshot = (
            runtime_state.get("metadata", {}).get("runtime")
            if runtime_state and isinstance(runtime_state.get("metadata"), dict)
            else None
        )

        async with self._client() as client:
            record = await client.mark_task_record_completed(
                task_id,
                TaskRecordCompletedPayload(
                    status=status,
                    result=result,
                    error=error,
                    completed_at=completed_at,
                    progress=final_progress,
                    message=final_message,
                    runtime_state=runtime_snapshot,
                ),
            )
            if record and record.execution_id:
                await ExecutionService(
                    dataservice=client,
                ).apply_task_transition(
                    record.execution_id,
                    commit=False,
                    status=(TaskStatus.SUCCESS.value if success else TaskStatus.FAILED.value),
                    result=result if isinstance(result, dict) else None,
                    error=error,
                    runtime_state=runtime_snapshot,
                    result_summary=result_summary,
                    artifact_ids=artifact_ids,
                    next_actions=next_actions,
                    advisory_code=None,
                    last_error=error,
                    started_at=record.started_at,
                    completed_at=completed_at,
                    message=final_message,
                    progress=final_progress,
                )
        if not record:
            return

        # Redis runtime cache (always derived from committed DB state)
        await self.set_task_state(
            task_id,
            status,
            progress=final_progress,
            message=final_message,
            metadata=runtime_state.get("metadata") if runtime_state else None,
        )

        # Post-commit: touch compute projection
        if record.execution_id:
            from src.compute.session_service import ComputeSessionService

            await ComputeSessionService().touch_session_by_execution(
                record.execution_id
            )

        workspace_id = str(payload.get("workspace_id")) if payload.get("workspace_id") else None
        if workspace_id:
            await publish_workspace_event(
                workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": task_id,
                        "execution_id": record.execution_id,
                        "task_type": record.task_type,
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
                            task_type=record.task_type,
                            payload=payload,
                            status=status,
                            progress=final_progress,
                            message=final_message,
                            error=error,
                            result=result if isinstance(result, dict) else result,
                            occurred_at=completed_at,
                            created_at=record.created_at,
                            started_at=record.started_at,
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
