"""Base task execution function."""

import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from celery import Task, shared_task

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationAttachmentStatePatchPayload,
)
from src.task.registry import (
    DOCUMENT_PREPROCESS_TASK,
    REFERENCE_PREPROCESS_TASK,
)

logger = logging.getLogger(__name__)
async def _maybe_await(value: Any) -> Any:
    """Await async values while tolerating sync test doubles."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _sync_document_preprocess_attachment_state(
    *,
    dataservice: AsyncDataServiceClient,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    status: str,
    result: dict[str, Any] | None = None,
    message: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    error: str | None = None,
) -> None:
    """Best-effort persistence of preprocessing task state onto source attachments."""
    if task_type != DOCUMENT_PREPROCESS_TASK:
        return
    await _sync_preprocess_attachment_state(
        dataservice=dataservice,
        task_id=task_id,
        payload=payload,
        status=status,
        result=result,
        message=message,
        progress=progress,
        current_step=current_step,
        error=error,
        log_label="document",
    )


async def _sync_reference_preprocess_attachment_state(
    *,
    dataservice: AsyncDataServiceClient,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    status: str,
    result: dict[str, Any] | None = None,
    message: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    error: str | None = None,
) -> None:
    """Best-effort persistence of reference preprocessing state onto attachments."""
    if task_type != REFERENCE_PREPROCESS_TASK:
        return
    await _sync_preprocess_attachment_state(
        dataservice=dataservice,
        task_id=task_id,
        payload=payload,
        status=status,
        result=result,
        message=message,
        progress=progress,
        current_step=current_step,
        error=error,
        log_label="reference",
    )


async def _sync_preprocess_attachment_state(
    *,
    dataservice: AsyncDataServiceClient,
    task_id: str,
    payload: dict[str, Any],
    status: str,
    result: dict[str, Any] | None = None,
    message: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    error: str | None = None,
    log_label: str,
) -> None:
    """Best-effort persistence of preprocessing task state onto attachments."""

    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return

    preprocess_payload = None
    if isinstance(result, dict) and isinstance(result.get("preprocess"), dict):
        preprocess_payload = result.get("preprocess")

    try:
        from src.services.thread_events import publish_thread_updated

        changed = await dataservice.patch_conversation_attachment_state(
            thread_id,
            ConversationAttachmentStatePatchPayload(
                thread_id=thread_id,
                task_id=task_id,
                state_key="preprocess",
                status=status,
                state_patch=dict(preprocess_payload or {}),
                message=message,
                progress=progress,
                current_step=current_step,
                error=error,
            ),
        )
        if changed:
            thread = await dataservice.get_conversation_thread(thread_id)
            if thread is not None:
                await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to sync %s preprocess attachment state for thread %s",
            log_label,
            thread_id,
            exc_info=True,
        )


def _execute_task_entry(
    self: Task,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
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

    runner = cast(
        Callable[[Awaitable[dict[str, Any]]], dict[str, Any]],
        run_worker_coroutine,
    )
    return runner(_execute_task_async(self, task_id, task_type, payload))


execute_task = shared_task(
    bind=True,
    name="src.task.tasks.execute_task",
)(_execute_task_entry)


async def _execute_task_async(
    celery_task: Task,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Async task execution logic."""
    from src.academic.cache.redis_client import redis_client
    from src.dataservice_client.provider import dataservice_client
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    await _maybe_await(redis_client.reset_client(close_current=False))
    if redis_client._client is None:
        await _maybe_await(redis_client.connect())

    # Get dependencies
    progress = ProgressTracker(
        redis_client,
        task_id,
        workspace_id=str(payload.get("workspace_id") or "") or None,
        thread_id=str(payload.get("thread_id") or "") or None,
        mission_id=str(payload.get("mission_id") or "") or None,
        task_type=task_type,
        worker_id=celery_task.request.hostname,
    )

    async with dataservice_client() as dataservice:
        store = TaskStore(redis_client, dataservice=dataservice)
        _task_start_time = time.perf_counter()
        from src.observability.prometheus import track_task_end, track_task_start

        try:
            await store.mark_task_started(task_id, worker_id=celery_task.request.hostname)
            await progress.update(0, "Task started")

            # Prometheus metrics
            track_task_start()

            # Dispatch to task-specific handler
            result = await _dispatch_task(task_type, payload, progress)

            track_task_end(task_type, time.perf_counter() - _task_start_time)

            success_message = str(result.get("message")) if isinstance(result, Mapping) and result.get("message") else "Task completed"
            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete(success_message)

            await _sync_document_preprocess_attachment_state(
                dataservice=dataservice,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="success",
                result=result,
                message=success_message,
                progress=100,
                current_step="complete",
            )
            await _sync_reference_preprocess_attachment_state(
                dataservice=dataservice,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="success",
                result=result,
                message=success_message,
                progress=100,
                current_step="complete",
            )
            return result

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            try:
                track_task_end(task_type, time.perf_counter() - _task_start_time)
            except Exception:
                pass
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))
            await _sync_document_preprocess_attachment_state(
                dataservice=dataservice,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="failed",
                message=str(e),
                error=str(e),
            )
            await _sync_reference_preprocess_attachment_state(
                dataservice=dataservice,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="failed",
                message=str(e),
                error=str(e),
            )
            raise


async def _dispatch_task(
    task_type: str,
    payload: dict[str, Any],
    progress: Any,
) -> dict[str, Any]:
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
    from src.task.handlers.document_preprocess_handler import execute_document_preprocess
    from src.task.handlers.reference_preprocess_handler import execute_reference_preprocess
    from src.task.registry import (
        DOCUMENT_PREPROCESS_TASK,
        REFERENCE_PREPROCESS_TASK,
        is_valid_task_type,
    )

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

    if task_type == DOCUMENT_PREPROCESS_TASK:
        logger.info("Dispatching document_preprocess task to document preprocess handler")
        return await execute_document_preprocess(payload, progress)

    if task_type == REFERENCE_PREPROCESS_TASK:
        logger.info("Dispatching reference_preprocess task to reference preprocess handler")
        return await execute_reference_preprocess(payload, progress)

    logger.error(
        "No executable mapping found for task type '%s'. Task type is registered but has no concrete dispatcher.",
        task_type,
    )
    raise ValueError(f"No executable mapping for task type: {task_type}")
