"""FastAPI dependencies for DataService."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request

from src.dataservice.common.actor import ActorContext
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork


async def get_actor_context(request: Request) -> ActorContext:
    """Build actor context from request headers."""
    return ActorContext.from_headers({key.lower(): value for key, value in request.headers.items()})


async def get_uow() -> AsyncGenerator[DataServiceUnitOfWork, None]:
    """Open one DataService unit of work for a request."""
    async with DataServiceUnitOfWork() as uow:
        yield uow
