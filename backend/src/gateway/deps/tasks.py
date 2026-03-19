"""Task-domain dependency factories."""

from collections.abc import AsyncGenerator

from src.academic.cache.redis_client import redis_client
from src.database import get_db_session
from src.task.service import TaskService
from src.task.store import TaskStore


async def get_task_service() -> AsyncGenerator[TaskService, None]:
    """Get task service instance."""
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        yield TaskService(store)
