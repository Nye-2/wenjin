"""Task-domain dependency factories."""

from collections.abc import AsyncGenerator

from src.academic.cache.redis_client import redis_client
from src.dataservice_client.provider import dataservice_client
from src.task.service import TaskService
from src.task.store import TaskStore


async def get_task_service() -> AsyncGenerator[TaskService, None]:
    """Get task service instance."""
    async with dataservice_client() as dataservice:
        store = TaskStore(redis_client, dataservice=dataservice)
        yield TaskService(store)
