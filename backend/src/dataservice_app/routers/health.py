"""DataService liveness and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.database.session import engine

router = APIRouter(tags=["health"])


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    """Process liveness."""
    return {"status": "healthy", "service": "dataservice"}


@router.get("/readyz", include_in_schema=False, response_model=None)
async def readyz() -> Any:
    """Dependency readiness."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "service": "dataservice", "database": {"status": "unhealthy", "error": str(exc)}},
        )
    return {"status": "healthy", "service": "dataservice", "database": {"status": "healthy"}}
