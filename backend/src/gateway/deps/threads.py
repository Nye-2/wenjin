"""Thread-domain dependency factories."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.gateway.deps.core import get_db
from src.services import ThreadService


async def get_thread_service(
    db: AsyncSession = Depends(get_db),
) -> ThreadService:
    """Get thread service instance."""
    return ThreadService(db)
