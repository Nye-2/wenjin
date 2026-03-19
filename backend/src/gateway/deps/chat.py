"""Chat-domain dependency factories."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.gateway.deps.core import get_db
from src.services import ChatThreadService


async def get_chat_thread_service(
    db: AsyncSession = Depends(get_db),
) -> ChatThreadService:
    """Get chat thread service instance."""
    return ChatThreadService(db)
