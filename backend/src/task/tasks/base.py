"""Base task execution function."""

import asyncio
import logging

from celery import shared_task

from src.task.registry import TaskStatus
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

            # Mark as completed
            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

            return result

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))
            raise


async def _dispatch_task(task_type: str, payload: dict, progress) -> dict:
    """Dispatch task to appropriate handler.

    Routes task execution to:
    1. SkillTaskHandler for skill-based tasks (deep_research, thesis_generation, etc.)
    2. Custom handlers for other task types

    Args:
        task_type: Type of task to execute
        payload: Task-specific parameters
        progress: ProgressTracker instance for progress reporting

    Returns:
        Task result dict

    Raises:
        ValueError: If task_type is unknown
    """
    from src.task.registry import is_valid_task_type

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

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
