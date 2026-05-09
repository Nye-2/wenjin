"""Base task execution function."""

import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from celery import Task, shared_task

from src.task.registry import (
    DOCUMENT_PREPROCESS_TASK,
    REFERENCE_PREPROCESS_TASK,
    WORKSPACE_FEATURE_TASK,
)

logger = logging.getLogger(__name__)


async def _maybe_await(value: Any) -> Any:
    """Await async values while tolerating sync test doubles."""
    if inspect.isawaitable(value):
        return await value
    return value


def _resolve_thread_skill(
    payload: Mapping[str, object],
    task_type: str,
) -> tuple[str, str | None]:
    skill_id = payload.get("skill_id")
    if isinstance(skill_id, str) and skill_id.strip():
        skill_name = payload.get("skill_name")
        normalized_skill_name = skill_name.strip() if isinstance(skill_name, str) and skill_name.strip() else None
        return skill_id.strip(), normalized_skill_name

    feature_id = payload.get("feature_id")
    if isinstance(feature_id, str) and feature_id.strip():
        return feature_id.strip(), None
    return task_type, None


async def _append_task_thread_message(
    *,
    db: Any,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Best-effort task result write-back into the originating thread."""
    if task_type in {DOCUMENT_PREPROCESS_TASK, REFERENCE_PREPROCESS_TASK}:
        return

    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return

    feature_id = str(payload.get("feature_id") or task_type).strip()
    if not feature_id:
        return

    try:
        from src.application.presenters.agent_result_card import (
            build_completion_result_card,
            build_failure_result_card,
        )
        from src.services.thread_events import publish_thread_updated
        from src.services.thread_service import ThreadService

        thread_service = ThreadService(db)
        thread = await thread_service.get_by_id(thread_id)
        if thread is None:
            return

        if error:
            reply = build_failure_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                error=error,
                failed_phase=str(payload.get("failed_phase") or "") or None,
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )
        else:
            reply = build_completion_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                result=result or {},
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )

        await thread_service.add_message(
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


async def _settle_workspace_feature_billing(
    *,
    db: Any,
    store: Any,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Settle token-based feature billing after successful task execution."""
    if task_type != WORKSPACE_FEATURE_TASK:
        return

    from src.services.credit_service import CreditService
    from src.services.thread_billing import normalize_token_usage

    usage = normalize_token_usage(result.get("token_usage"))
    if usage is None:
        return

    # Phase 3: Unified path — payload is the sole source of truth.
    user_id = str(payload.get("user_id") or payload.get("created_by") or "").strip()
    workspace_id = str(payload.get("workspace_id") or "").strip() or None

    if not user_id:
        logger.warning("Cannot settle billing: no user_id for task %s", task_id)
        return

    feature_id = str(payload.get("feature_id") or task_record.feature_id if task_record else "").strip()
    if not feature_id:
        return

    feature_name = str(payload.get("feature_name") or feature_id).strip()
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    billing = await CreditService(db).consume_for_feature_usage(
        user_id=user_id,
        feature_id=feature_id,
        token_usage=usage,
        workspace_id=workspace_id,
        task_id=task_id,
        description=f"{feature_name} token 扣费",
        metadata={
            "workspace_type": payload.get("workspace_type"),
            "handler_key": payload.get("handler_key"),
            "params": params,
        },
    )
    result["billing"] = billing.as_metadata()


async def _sync_document_preprocess_attachment_state(
    *,
    db: Any,
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

    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return

    preprocess_payload = None
    if isinstance(result, dict) and isinstance(result.get("preprocess"), dict):
        preprocess_payload = result.get("preprocess")

    try:
        from src.services.thread_events import publish_thread_updated
        from src.services.thread_service import ThreadService

        thread_service = ThreadService(db)
        thread = await thread_service.get_by_id(thread_id)
        if thread is None:
            return

        changed = await thread_service.update_attachment_preprocess_state(
            thread,
            task_id=task_id,
            status=status,
            preprocess=preprocess_payload,
            message=message,
            progress=progress,
            current_step=current_step,
            error=error,
        )
        if changed:
            await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to sync document preprocess attachment state for thread %s",
            thread_id,
            exc_info=True,
        )


async def _sync_reference_preprocess_attachment_state(
    *,
    db: Any,
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

    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return

    preprocess_payload = None
    if isinstance(result, dict) and isinstance(result.get("preprocess"), dict):
        preprocess_payload = result.get("preprocess")

    try:
        from src.services.thread_events import publish_thread_updated
        from src.services.thread_service import ThreadService

        thread_service = ThreadService(db)
        thread = await thread_service.get_by_id(thread_id)
        if thread is None:
            return

        changed = await thread_service.update_attachment_preprocess_state(
            thread,
            task_id=task_id,
            status=status,
            preprocess=preprocess_payload,
            message=message,
            progress=progress,
            current_step=current_step,
            error=error,
        )
        if changed:
            await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to sync reference preprocess attachment state for thread %s",
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
    from src.database import get_db_session, reset_db_engine
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    # Reset event-loop-bound resources for this worker process.
    # Celery forks workers after module import, so global singletons
    # (redis_client, DB engine) may hold Futures from the parent loop.
    await _maybe_await(reset_db_engine(dispose_current=False))
    await _maybe_await(redis_client.reset_client(close_current=False))
    if redis_client._client is None:
        await _maybe_await(redis_client.connect())

    # Get dependencies
    progress = ProgressTracker(
        redis_client,
        task_id,
        workspace_id=str(payload.get("workspace_id") or "") or None,
        thread_id=str(payload.get("thread_id") or "") or None,
        execution_session_id=str(payload.get("execution_session_id") or "") or None,
        task_type=task_type,
        feature_id=str(payload.get("feature_id") or "") or None,
        worker_id=celery_task.request.hostname,
    )

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)

        # Phase 2: Unified execution model — atomic dual-write within the same session.
        execution_record_id: str | None = None
        if task_type == WORKSPACE_FEATURE_TASK:
            from src.services.execution_service import ExecutionService

            execution_service = ExecutionService(db)
            # Gateway may have already created the ExecutionRecord and passed
            # its id in the payload.  Re-use it to avoid duplicates.
            existing_execution_id = str(payload.get("execution_id") or "").strip()
            if existing_execution_id:
                execution_record = await execution_service.get_by_id(existing_execution_id)
                if execution_record is not None:
                    execution_record_id = execution_record.id
            if not execution_record_id:
                execution_record = await execution_service.create_execution(
                    execution_type="feature",
                    user_id=str(payload.get("user_id") or payload.get("created_by") or ""),
                    workspace_id=str(payload.get("workspace_id") or "") or None,
                    thread_id=str(payload.get("thread_id") or "") or None,
                    feature_id=str(payload.get("feature_id") or "") or None,
                    entry_skill_id=str(payload.get("skill_id") or "") or None,
                    workspace_type=str(payload.get("workspace_type") or "") or None,
                    params=dict(payload.get("params") or {}),
                    commit=False,
                )
                execution_record_id = execution_record.id
                payload["execution_id"] = execution_record_id

        try:
            # Phase 3: legacy TaskRecord writes are skipped for feature tasks inside
            # the store layer, but we still call the method so it can do minimal
            # status updates needed for idempotency (e.g. mark as running).
            await store.mark_task_started(task_id, worker_id=celery_task.request.hostname)
            await progress.update(0, "Task started")

            # Phase 2+: Start execution tracking
            if execution_record_id:
                from src.services.execution_service import ExecutionService

                execution_service = ExecutionService(db)
                await execution_service.start_execution(execution_record_id, commit=False)
                from src.services.execution_event_publisher import publish_execution_event

                await publish_execution_event(
                    execution_record_id,
                    "execution.status",
                    {"status": "running", "progress": 0, "message": "Task started"},
                    workspace_id=str(payload.get("workspace_id") or "") or None,
                )

            # Prometheus metrics
            _task_start_time = time.perf_counter()
            from src.observability.prometheus import track_task_end, track_task_start

            track_task_start()

            # Track agent status in Redis
            thread_id = payload.get("thread_id")
            workspace_id = str(payload.get("workspace_id") or "") or None
            thread_skill, thread_skill_name = _resolve_thread_skill(payload, task_type)
            if thread_id:
                from src.services.thread_events import set_thread_status

                await set_thread_status(
                    workspace_id,
                    str(thread_id),
                    status="running",
                    skill=thread_skill,
                    skill_name=thread_skill_name,
                    subagent_count=0,
                )

            # Dispatch to task-specific handler
            result = await _dispatch_task(task_type, payload, progress)
            await _settle_workspace_feature_billing(
                db=db,
                store=store,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                result=result,
            )

            if thread_id:
                from src.services.thread_events import set_thread_status

                await set_thread_status(
                    workspace_id,
                    str(thread_id),
                    status="completed",
                    skill=thread_skill,
                    skill_name=thread_skill_name,
                    subagent_count=0,
                )

            track_task_end(task_type, time.perf_counter() - _task_start_time)

            # Phase 2+: Complete execution record on success (same DB session)
            if execution_record_id:
                from src.services.execution_service import ExecutionService

                execution_service = ExecutionService(db)
                await execution_service.complete_execution(
                    execution_record_id,
                    status="completed",
                    result=result if isinstance(result, dict) else None,
                    result_summary=str(result.get("message")) if isinstance(result, dict) else None,
                    commit=False,
                )
                from src.services.execution_event_publisher import (
                    publish_execution_event,
                    publish_execution_stream_end,
                )

                await publish_execution_event(
                    execution_record_id,
                    "execution.completed",
                    {
                        "status": "completed",
                        "result": result if isinstance(result, dict) else {},
                    },
                    workspace_id=str(payload.get("workspace_id") or "") or None,
                )
                await publish_execution_stream_end(execution_record_id)

            # Phase 3: legacy TaskRecord writes are skipped for feature tasks inside
            # the store layer, but we still call the method so it can do minimal
            # status updates needed for idempotency (e.g. mark as completed).
            success_message = str(result.get("message")) if isinstance(result, Mapping) and result.get("message") else "Task completed"
            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete(success_message)

            # Phase 3: Explicit workspace.refresh when unified (mark_task_completed normally does this)
            if task_type == WORKSPACE_FEATURE_TASK:
                workspace_id = str(payload.get("workspace_id") or "").strip()
                if workspace_id and isinstance(result, dict):
                    refresh_targets = ["dashboard"]
                    for target in result.get("refresh_targets") or []:
                        if isinstance(target, str) and target not in refresh_targets:
                            refresh_targets.append(target)
                    from src.workspace_events import publish_workspace_event

                    await publish_workspace_event(
                        workspace_id,
                        "workspace.refresh",
                        {"refresh_targets": refresh_targets},
                    )

            await _sync_document_preprocess_attachment_state(
                db=db,
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
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="success",
                result=result,
                message=success_message,
                progress=100,
                current_step="complete",
            )
            await _append_task_thread_message(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                result=result,
            )

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

                    # Phase 3: Unified path — payload is the sole source of truth.
                    user_id = str(payload.get("user_id") or payload.get("created_by") or "").strip()
                    if user_id:
                        credit_service = CreditService(db)
                        refund_tx = await credit_service.refund_failed_task(
                            user_id=user_id,
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
            workspace_id = str(payload.get("workspace_id") or "") or None
            if thread_id:
                from src.services.thread_events import set_thread_status

                await set_thread_status(
                    workspace_id,
                    str(thread_id),
                    status="failed",
                    skill=thread_skill,
                    skill_name=thread_skill_name,
                    subagent_count=0,
                )

            # Phase 2+: Complete execution record on failure (same DB session)
            if execution_record_id:
                from src.services.execution_service import ExecutionService

                execution_service = ExecutionService(db)
                await execution_service.complete_execution(
                    execution_record_id,
                    status="failed",
                    error=str(e),
                    commit=False,
                )
                from src.services.execution_event_publisher import (
                    publish_execution_event,
                    publish_execution_stream_end,
                )

                await publish_execution_event(
                    execution_record_id,
                    "execution.error",
                    {"status": "failed", "error": str(e)},
                    workspace_id=str(payload.get("workspace_id") or "") or None,
                )
                await publish_execution_stream_end(execution_record_id)

            # Phase 3: legacy TaskRecord writes are skipped for feature tasks inside
            # the store layer, but we still call the method so it can do minimal
            # status updates needed for idempotency (e.g. mark as failed).
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))
            await _sync_document_preprocess_attachment_state(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="failed",
                message=str(e),
                error=str(e),
            )
            await _sync_reference_preprocess_attachment_state(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                status="failed",
                message=str(e),
                error=str(e),
            )
            await _append_task_thread_message(
                db=db,
                task_id=task_id,
                task_type=task_type,
                payload=payload,
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
    from src.task.handlers.workspace_feature_handler import (
        execute_workspace_feature,
    )
    from src.task.registry import (
        DOCUMENT_PREPROCESS_TASK,
        REFERENCE_PREPROCESS_TASK,
        WORKSPACE_FEATURE_TASK,
        is_valid_task_type,
    )

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

    if task_type == WORKSPACE_FEATURE_TASK:
        logger.info("Dispatching workspace_feature task to workspace feature handler")
        return await execute_workspace_feature(payload, progress)

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
