"""Task executor abstraction — dual-mode (Celery / local asyncio)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

from src.config.app_config import celery_settings
from src.observability.prometheus import track_task_end, track_task_start

logger = logging.getLogger(__name__)


class TaskExecutor(Protocol):
    """Protocol for task execution backends."""

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None: ...


class CeleryExecutor:
    """Submit tasks to Celery broker queue."""

    def __init__(self, celery_app=None):
        if celery_app is None:
            from src.task import celery_app as _app
            celery_app = _app
        self._celery_app = celery_app

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        self._celery_app.send_task(
            "src.task.tasks.execute_task",
            args=[task_id, task_type, payload],
            queue=queue,
            priority=priority,
            task_id=task_id,
        )


class LocalExecutor:
    """Execute tasks in-process via asyncio (dev / low-traffic fallback)."""

    def __init__(self, max_concurrency: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict[str, asyncio.Task] = {}

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        task = asyncio.create_task(self._guarded_run(task_id, task_type, payload))
        self._tasks[task_id] = task

        def _cleanup(_done: asyncio.Task) -> None:
            self._tasks.pop(task_id, None)

        task.add_done_callback(_cleanup)

    async def _guarded_run(self, task_id: str, task_type: str, payload: dict) -> None:
        async with self._semaphore:
            await _run_task_locally(task_id, task_type, payload)

    def cancel(self, task_id: str) -> bool:
        """Cancel a local in-process task by id."""
        task = self._tasks.get(task_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True


async def _run_task_locally(task_id: str, task_type: str, payload: dict) -> None:
    """Run a task in the current process, reusing the Celery task logic."""
    from src.academic.cache.redis_client import redis_client
    from src.academic.services import ArtifactService
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    if redis_client._client is None:
        await redis_client.connect()

    progress = ProgressTracker(
        redis_client,
        task_id,
        workspace_id=str(payload.get("workspace_id") or "") or None,
        thread_id=str(payload.get("thread_id") or "") or None,
        task_type=task_type,
        feature_id=str(payload.get("feature_id") or "") or None,
    )

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        try:
            await store.mark_task_started(task_id, worker_id="local-executor")
            await progress.update(0, "Task started")

            # Prometheus metrics
            track_task_start()
            _task_start_time = time.perf_counter()

            # Track agent status in Redis
            thread_id = payload.get("thread_id")
            if thread_id:
                try:
                    await redis_client.set_agent_status(
                        thread_id,
                        "running",
                        skill=task_type,
                        subagent_count=0,
                    )
                except Exception:
                    logger.debug("Failed to set agent status for thread %s", thread_id)

            from src.task.tasks.base import _dispatch_task

            result = await _dispatch_task(task_type, payload, progress)

            # Deep research artifact persistence (same as base.py)
            if task_type == "deep_research":
                artifacts = result.get("artifacts") or []
                if isinstance(artifacts, list) and artifacts:
                    service = ArtifactService(db)
                    workspace_id = str(payload.get("workspace_id") or "")
                    persisted_refs: list[dict] = []
                    for artifact in artifacts:
                        art_type = artifact.get("type", "other")
                        content = artifact.get("content", {}) or {}
                        title = artifact.get("title") or {
                            "literature_review": "Deep Research 文献综述",
                            "research_ideas": "Deep Research 研究创意",
                            "gap_analysis": "Deep Research 研究空白分析",
                        }.get(art_type, f"Deep Research {art_type}")
                        record = await service.create(
                            workspace_id=workspace_id,
                            type=art_type,
                            title=title,
                            content=content,
                            created_by_skill=artifact.get("created_by_skill") or "deep-research",
                        )
                        persisted_refs.append({"id": str(record.id), "type": record.type, "title": record.title or ""})
                    result["artifacts"] = persisted_refs
                    refresh_targets = result.get("refresh_targets") or []
                    if "artifacts" not in refresh_targets:
                        result["refresh_targets"] = [*refresh_targets, "artifacts"]

            if thread_id:
                try:
                    await redis_client.set_agent_status(
                        thread_id,
                        "completed",
                        subagent_count=0,
                    )
                except Exception:
                    logger.debug("Failed to update agent status for thread %s", thread_id)

            track_task_end(task_type, time.perf_counter() - _task_start_time)

            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

        except Exception as e:
            logger.exception("Local task %s failed: %s", task_id, e)
            try:
                track_task_end(task_type, time.perf_counter() - _task_start_time)
            except Exception:
                pass
            credit_transaction_id = payload.get("credit_transaction_id")
            if credit_transaction_id:
                try:
                    from src.services.credit_service import CreditService

                    task_record = await store.get_task_record(task_id)
                    if task_record is not None:
                        credit_service = CreditService(db)
                        await credit_service.refund_failed_task(
                            user_id=task_record.user_id,
                            original_transaction_id=str(credit_transaction_id),
                            reason="任务执行失败退款",
                            task_id=task_id,
                        )
                except Exception:
                    logger.exception("Failed to refund credits for task %s", task_id)
            thread_id = payload.get("thread_id")
            if thread_id:
                try:
                    await redis_client.set_agent_status(
                        thread_id,
                        "failed",
                        subagent_count=0,
                    )
                except Exception:
                    logger.debug("Failed to update agent status for thread %s", thread_id)

            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))


def get_executor() -> TaskExecutor:
    """Factory: return CeleryExecutor or LocalExecutor based on settings."""
    global _CELERY_EXECUTOR, _LOCAL_EXECUTOR

    if celery_settings.enabled:
        if _CELERY_EXECUTOR is None:
            _CELERY_EXECUTOR = CeleryExecutor()
        return _CELERY_EXECUTOR

    if _LOCAL_EXECUTOR is None:
        _LOCAL_EXECUTOR = LocalExecutor()
    return _LOCAL_EXECUTOR


def cancel_local_task(task_id: str) -> bool:
    """Cancel task in local executor mode."""
    if _LOCAL_EXECUTOR is None:
        return False
    return _LOCAL_EXECUTOR.cancel(task_id)


_CELERY_EXECUTOR: CeleryExecutor | None = None
_LOCAL_EXECUTOR: LocalExecutor | None = None
