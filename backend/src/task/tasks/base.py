"""Base task execution function."""

import asyncio
import logging

from celery import shared_task

from src.task.handlers.skill_handler import get_skill_task_handler

logger = logging.getLogger(__name__)


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
    return asyncio.run(_execute_task_async(self, task_id, task_type, payload))


async def _execute_task_async(
    celery_task,
    task_id: str,
    task_type: str,
    payload: dict,
) -> dict:
    """Async task execution logic."""
    from src.academic.cache.redis_client import redis_client
    from src.academic.services import ArtifactService
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    # Connect Redis if needed
    if redis_client._client is None:
        await redis_client.connect()

    # Get dependencies
    progress = ProgressTracker(redis_client, task_id)

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)

        try:
            # Mark task as started
            await store.mark_task_started(task_id, worker_id=celery_task.request.hostname)
            await progress.update(0, "Task started")

            # Dispatch to task-specific handler
            result = await _dispatch_task(task_type, payload, progress)

            # Persist artifacts for skill-based deep research tasks so they
            # become first-class workspace artifacts.
            if task_type == "deep_research":
                artifacts = result.get("artifacts") or []
                if isinstance(artifacts, list) and artifacts:
                    service = ArtifactService(db)
                    workspace_id = str(payload.get("workspace_id") or "")
                    persisted_refs: list[dict] = []
                    for artifact in artifacts:
                        # Expect skill handler to return dicts with at least "type" and "content"
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
                        persisted_refs.append(
                            {
                                "id": str(record.id),
                                "type": record.type,
                                "title": record.title or "",
                            }
                        )

                    # Replace artifacts payload with lightweight references
                    result["artifacts"] = persisted_refs
                    refresh_targets = result.get("refresh_targets") or []
                    if "artifacts" not in refresh_targets:
                        result["refresh_targets"] = [*refresh_targets, "artifacts"]

            # Mark as completed
            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

            return result

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
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
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))
            raise


async def _dispatch_task(task_type: str, payload: dict, progress) -> dict:
    """Dispatch task to appropriate handler.

    Routes task execution to:
    1. Custom workflow handlers for thesis and workspace features
    2. SkillTaskHandler for registered skill-based tasks
    3. Placeholder execution for task types without concrete handlers

    Args:
        task_type: Type of task to execute
        payload: Task-specific parameters
        progress: ProgressTracker instance for progress reporting

    Returns:
        Task result dict

    Raises:
        ValueError: If task_type is unknown
    """
    from src.task.handlers.workspace_feature_handler import (
        execute_thesis_generation,
        execute_workspace_feature,
    )
    from src.task.registry import is_valid_task_type

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

    if task_type == "thesis_generation":
        logger.info("Dispatching thesis_generation task to thesis workflow handler")
        return await execute_thesis_generation(payload, progress)

    if task_type == "workspace_feature":
        logger.info("Dispatching workspace_feature task to workspace feature handler")
        return await execute_workspace_feature(payload, progress)

    # Get the skill task handler
    handler = get_skill_task_handler()

    # Check if this task type maps to a skill
    skill_name = handler.get_skill_name(task_type)

    if skill_name:
        # Execute via skill handler
        logger.info(f"Dispatching task type '{task_type}' to skill '{skill_name}'")
        return await handler.execute_skill(task_type, payload, progress)
    else:
        # Fallback: placeholder implementation for task types without skill mapping
        logger.info(f"No skill mapping for task type '{task_type}', using placeholder")
        return await _execute_placeholder(task_type, payload, progress)


async def _execute_placeholder(task_type: str, payload: dict, progress) -> dict:
    """Placeholder execution for task types without skill implementations.

    This should be replaced with actual implementations or skill mappings.

    Args:
        task_type: Type of task
        payload: Task parameters
        progress: ProgressTracker instance

    Returns:
        Placeholder result dict
    """
    await progress.update(25, f"Processing {task_type}...")
    await asyncio.sleep(1)

    await progress.update(50, f"Executing {task_type} logic...")
    await asyncio.sleep(1)

    await progress.update(75, "Finalizing...")

    return {
        "task_type": task_type,
        "status": "completed",
        "message": f"Task '{task_type}' executed successfully (placeholder)",
        "payload_received": payload,
    }
