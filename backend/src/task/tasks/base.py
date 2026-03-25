"""Base task execution function."""

import logging
import time
from collections.abc import Mapping

from celery import shared_task

logger = logging.getLogger(__name__)


def _resolve_thread_skill(payload: Mapping[str, object], task_type: str) -> str:
    feature_id = payload.get("feature_id")
    if isinstance(feature_id, str) and feature_id.strip():
        return feature_id
    return task_type


async def _append_task_chat_message(
    *,
    db,
    task_id: str,
    task_type: str,
    payload: dict,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Best-effort task result write-back into the originating chat thread."""
    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return

    feature_id = str(payload.get("feature_id") or task_type).strip()
    if not feature_id:
        return

    try:
        from src.agents.lead_agent.feature_bridge import (
            build_feature_task_completion_card,
            build_feature_task_failure_card,
        )
        from src.services.chat_thread_events import publish_thread_updated
        from src.services.chat_thread_service import ChatThreadService

        chat_thread_service = ChatThreadService(db)
        thread = await chat_thread_service.get_by_id(thread_id)
        if thread is None:
            return

        if error:
            reply = build_feature_task_failure_card(
                feature_id=feature_id,
                task_id=task_id,
                payload=payload,
                error=error,
            )
        else:
            reply = build_feature_task_completion_card(
                feature_id=feature_id,
                task_id=task_id,
                payload=payload,
                result=result or {},
            )

        await chat_thread_service.add_message(
            thread,
            role="assistant",
            content=reply.content,
            blocks=reply.blocks,
            metadata=reply.metadata,
        )
        await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to append task result to thread %s",
            thread_id,
            exc_info=True,
        )


@shared_task(bind=True, name="src.task.tasks.execute_task")
def execute_task(self, task_id: str, task_type: str, payload: dict) -> dict:
    """Execute a task based on its type.

    This is the main entry point for all async tasks.
    Task-specific handlers are dispatched based on task_type.

    Args:
        self: Celery task instance
        task_id: Unique task identifier
        task_type: Type of task to execute
        payload: Task-specific parameters

    Returns:
        Task result dict
    """
    from src.task.worker import run_worker_coroutine

    return run_worker_coroutine(_execute_task_async(self, task_id, task_type, payload))


async def _execute_task_async(
    celery_task,
    task_id: str,
    task_type: str,
    payload: dict,
) -> dict:
    """Async task execution logic."""
    from src.academic.cache.redis_client import redis_client
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    # Connect Redis if needed
    if redis_client._client is None:
        await redis_client.connect()

    # Get dependencies
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
            # Mark task as started
            await store.mark_task_started(task_id, worker_id=celery_task.request.hostname)
            await progress.update(0, "Task started")

            # Prometheus metrics
            from src.observability.prometheus import track_task_end, track_task_start

            track_task_start()
            _task_start_time = time.perf_counter()

            # Track agent status in Redis
            thread_id = payload.get("thread_id")
            if thread_id:
                from src.services.chat_thread_events import set_thread_status

                await set_thread_status(
                    str(payload.get("workspace_id") or "") or None,
                    str(thread_id),
                    status="running",
                    skill=_resolve_thread_skill(payload, task_type),
                    subagent_count=0,
                )

            # Dispatch to task-specific handler
            result = await _dispatch_task(task_type, payload, progress)

            if thread_id:
                from src.services.chat_thread_events import set_thread_status

                await set_thread_status(
                    str(payload.get("workspace_id") or "") or None,
                    str(thread_id),
                    status="completed",
                    skill=_resolve_thread_skill(payload, task_type),
                    subagent_count=0,
                )

            track_task_end(task_type, time.perf_counter() - _task_start_time)

            # Terminal state: single DB write + Pub/Sub broadcast
            # mark_task_completed → DB + Redis (authoritative)
            # progress.complete  → Redis + Pub/Sub (SSE notification only)
            await store.mark_task_completed(task_id, success=True, result=result)
            await _append_task_chat_message(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                result=result,
            )
            await progress.complete("Task completed successfully")

            return result

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
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
                        refund_tx = await credit_service.refund_failed_task(
                            user_id=task_record.user_id,
                            original_transaction_id=str(credit_transaction_id),
                            reason="任务执行失败退款",
                            task_id=task_id,
                        )
                        if refund_tx is not None:
                            logger.info(
                                "Refunded %s credits for failed task %s",
                                refund_tx.amount,
                                task_id,
                            )
                except Exception:
                    logger.exception(
                        "Failed to refund credits for task %s (tx=%s)",
                        task_id,
                        credit_transaction_id,
                    )
            thread_id = payload.get("thread_id")
            if thread_id:
                from src.services.chat_thread_events import set_thread_status

                await set_thread_status(
                    str(payload.get("workspace_id") or "") or None,
                    str(thread_id),
                    status="failed",
                    skill=_resolve_thread_skill(payload, task_type),
                    subagent_count=0,
                )

            # Terminal state: single DB write + Pub/Sub broadcast
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await _append_task_chat_message(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                error=str(e),
            )
            await progress.fail(str(e))
            raise


async def _dispatch_task(task_type: str, payload: dict, progress) -> dict:
    """Dispatch task to appropriate handler.

    Routes task execution to canonical task handlers.

    Args:
        task_type: Type of task to execute
        payload: Task-specific parameters
        progress: ProgressTracker instance for progress reporting

    Returns:
        Task result dict

    Raises:
        ValueError: If task_type is unknown
    """
    from src.task.handlers.paper_extraction_handler import (
        execute_paper_extraction,
    )
    from src.task.handlers.workspace_feature_handler import (
        execute_workspace_feature,
    )
    from src.task.registry import (
        PAPER_EXTRACTION_TASK,
        WORKSPACE_FEATURE_TASK,
        is_valid_task_type,
    )

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

    if task_type == WORKSPACE_FEATURE_TASK:
        logger.info("Dispatching workspace_feature task to workspace feature handler")
        return await execute_workspace_feature(payload, progress)

    if task_type == PAPER_EXTRACTION_TASK:
        logger.info("Dispatching paper_extraction task to paper extraction handler")
        return await execute_paper_extraction(payload, progress)

    logger.error(
        "No executable mapping found for task type '%s'. "
        "Task type is registered but has no concrete dispatcher.",
        task_type,
    )
    raise ValueError(f"No executable mapping for task type: {task_type}")
