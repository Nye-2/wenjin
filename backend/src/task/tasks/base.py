"""Base task execution function."""

import copy
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from celery import Task, shared_task

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagesRebuildPayload,
    ConversationThreadUpdatePayload,
)
from src.task.registry import (
    DOCUMENT_PREPROCESS_TASK,
    REFERENCE_PREPROCESS_TASK,
)

logger = logging.getLogger(__name__)
_LAST_MESSAGE_PREVIEW_LIMIT = 120


def _truncate_message_preview(content: str | None, limit: int = _LAST_MESSAGE_PREVIEW_LIMIT) -> str | None:
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _conversation_message_to_bridge(message: Any) -> dict[str, Any]:
    timestamp = getattr(message, "timestamp", None)
    result: dict[str, Any] = {
        "role": str(getattr(message, "role", "") or ""),
        "content": str(getattr(message, "content", "") or ""),
        "timestamp": timestamp.isoformat() if timestamp else None,
    }
    metadata = getattr(message, "metadata_json", None)
    if isinstance(metadata, Mapping) and metadata:
        result["metadata"] = dict(metadata)
    blocks = getattr(message, "blocks", None)
    if isinstance(blocks, list) and blocks:
        result["blocks"] = [
            dict(block.payload_json)
            for block in blocks
            if isinstance(getattr(block, "payload_json", None), Mapping)
        ]
    return result


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
    dataservice: AsyncDataServiceClient,
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

        thread = await dataservice.get_conversation_thread(thread_id)
        if thread is None:
            return

        if error:
            reply = build_failure_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_id=str(payload.get("execution_id") or "") or None,
                payload=payload,
                error=error,
                failed_phase=str(payload.get("failed_phase") or "") or None,
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )
        else:
            completion_payload = dict(payload)
            completion_payload.setdefault("workspace_id", getattr(thread, "workspace_id", None))
            reply = build_completion_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_id=str(payload.get("execution_id") or "") or None,
                payload=completion_payload,
                result=result or {},
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )

        persisted = await dataservice.append_conversation_message(
            thread_id,
            ConversationMessageCreatePayload(
                thread_id=thread_id,
                user_id=str(thread.user_id),
                workspace_id=thread.workspace_id,
                role="assistant",
                content=reply.content,
                sequence_index=max(int(thread.message_count or 0), 0),
                timestamp=datetime.now(UTC),
                blocks=reply.blocks or [],
                metadata=reply.metadata or {},
            ),
        )
        if persisted is not None:
            thread.message_count = int(persisted.sequence_index) + 1
        else:
            thread.message_count = int(thread.message_count or 0) + 1
        thread.last_message_role = "assistant"
        thread.last_message_preview = _truncate_message_preview(reply.content)
        thread.updated_at = persisted.timestamp if persisted is not None else datetime.now(UTC)
        await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to append task result to thread %s",
            thread_id,
            exc_info=True,
        )


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

        thread = await dataservice.get_conversation_thread(thread_id)
        if thread is None:
            return

        await dataservice.lock_conversation_thread(thread_id)
        raw_messages = await dataservice.list_conversation_messages(thread_id)
        messages = copy.deepcopy(
            [_conversation_message_to_bridge(message_item) for message_item in raw_messages]
        )
        changed = _apply_attachment_preprocess_state(
            messages,
            task_id=task_id,
            status=status,
            preprocess=preprocess_payload,
            message=message,
            progress=progress,
            current_step=current_step,
            error=error,
        )
        if changed:
            now = datetime.now(UTC)
            updated = await dataservice.update_conversation_thread(
                thread_id,
                ConversationThreadUpdatePayload(
                    message_count=len(messages),
                    updated_at=now,
                ),
            )
            await dataservice.rebuild_conversation_messages(
                thread_id,
                ConversationMessagesRebuildPayload(
                    thread_id=thread_id,
                    user_id=str(thread.user_id),
                    workspace_id=thread.workspace_id,
                    messages=messages,
                ),
            )
            if updated is not None:
                thread = updated
            thread.message_count = len(messages)
            thread.updated_at = now
            await publish_thread_updated(thread)
    except Exception:
        logger.warning(
            "Failed to sync %s preprocess attachment state for thread %s",
            log_label,
            thread_id,
            exc_info=True,
        )


def _apply_attachment_preprocess_state(
    messages: list[dict[str, Any]],
    *,
    task_id: str,
    status: str,
    preprocess: dict[str, Any] | None = None,
    message: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    error: str | None = None,
) -> bool:
    resolved_task_id = task_id.strip()
    if not resolved_task_id:
        return False

    changed = False
    for message_item in messages:
        if not isinstance(message_item, dict):
            continue
        metadata = message_item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        attachments = metadata.get("attachments")
        if not isinstance(attachments, list):
            continue

        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            attachment_metadata = attachment.get("metadata")
            if not isinstance(attachment_metadata, dict):
                continue
            current_preprocess = attachment_metadata.get("preprocess")
            if not isinstance(current_preprocess, dict):
                continue
            if current_preprocess.get("task_id") != resolved_task_id:
                continue

            next_preprocess = dict(current_preprocess)
            if isinstance(preprocess, dict):
                next_preprocess.update(preprocess)
            next_preprocess["task_id"] = resolved_task_id
            if status == "success" and isinstance(preprocess, dict):
                next_preprocess["status"] = str(
                    preprocess.get("status")
                    or next_preprocess.get("status")
                    or "succeeded"
                )
            elif status:
                next_preprocess["status"] = status
            if message:
                next_preprocess["message"] = message
            if progress is not None:
                next_preprocess["progress"] = progress
            if current_step:
                next_preprocess["current_step"] = current_step
            elif current_step == "":
                next_preprocess.pop("current_step", None)
            if error:
                next_preprocess["error"] = error
                next_preprocess["status"] = "failed"
            elif next_preprocess.get("status") == "succeeded":
                next_preprocess.pop("error", None)

            attachment_metadata["preprocess"] = next_preprocess
            markdown_paths = next_preprocess.get("markdown_paths")
            if isinstance(markdown_paths, list) and markdown_paths:
                attachment_metadata["preprocessed_markdown_paths"] = markdown_paths
            changed = True

    return changed


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
        execution_id=str(payload.get("execution_id") or "") or None,
        task_type=task_type,
        feature_id=str(payload.get("feature_id") or "") or None,
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
            await _append_task_thread_message(
                dataservice=dataservice,
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
                        credit_service = CreditService()
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
            await _append_task_thread_message(
                dataservice=dataservice,
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
