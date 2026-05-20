"""Standalone DataService FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.dataservice.common.api import envelope_error
from src.dataservice.common.errors import DataServiceError
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """DataService lifespan."""
    setup_logging(level="INFO")
    logger.info("Wenjin DataService starting up...")

    from src.database import init_db

    await init_db()
    yield

    logger.info("Wenjin DataService shutting down...")
    from src.database import close_db

    await close_db()


app = FastAPI(
    title="Wenjin DataService",
    description="问津 DataService — canonical data ownership and transaction boundary",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(DataServiceError)
async def handle_dataservice_error(request: Request, exc: DataServiceError) -> JSONResponse:
    """Return stable error envelopes for typed DataService failures."""
    trace_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    return JSONResponse(
        status_code=exc.http_status,
        content=envelope_error(
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            trace_id=trace_id,
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return stable envelopes for unexpected failures."""
    logger.exception("Unhandled DataService error: %s", exc)
    trace_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    return JSONResponse(
        status_code=500,
        content=envelope_error(
            code="INTERNAL_ERROR",
            message="DataService internal error",
            trace_id=trace_id,
        ),
    )


from .routers import catalog, conversation, execution, health, review, workspace  # noqa: E402

app.include_router(catalog.router)
app.include_router(conversation.router)
app.include_router(execution.router)
app.include_router(health.router)
app.include_router(review.router)
app.include_router(workspace.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, Any]:
    """Root service identity."""
    return {"service": "wenjin-dataservice", "status": "healthy"}
