"""Task executor abstraction — dual-mode (Celery / local asyncio)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from src.config.app_config import celery_settings

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

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        asyncio.create_task(self._guarded_run(task_id, task_type, payload))

    async def _guarded_run(self, task_id: str, task_type: str, payload: dict) -> None:
        async with self._semaphore:
            await _run_task_locally(task_id, task_type, payload)


async def _run_task_locally(task_id: str, task_type: str, payload: dict) -> None:
    """Run a task in the current process, reusing the Celery task logic."""
    from src.academic.cache.redis_client import redis_client
    from src.academic.services import ArtifactService
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    if redis_client._client is None:
        await redis_client.connect()

    progress = ProgressTracker(redis_client, task_id)

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        try:
            await store.mark_task_started(task_id, worker_id="local-executor")
            await progress.update(0, "Task started")

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

            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

        except Exception as e:
            logger.exception("Local task %s failed: %s", task_id, e)
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
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))


def get_executor() -> TaskExecutor:
    """Factory: return CeleryExecutor or LocalExecutor based on settings."""
    if celery_settings.enabled:
        return CeleryExecutor()
    return LocalExecutor()
