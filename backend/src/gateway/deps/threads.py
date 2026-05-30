"""Thread-domain dependency factories."""

from fastapi import Depends

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client
from src.services import ThreadService


async def get_thread_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ThreadService:
    """Get thread service instance."""
    return ThreadService(dataservice=dataservice)
