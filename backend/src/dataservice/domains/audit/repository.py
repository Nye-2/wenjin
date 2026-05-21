"""Audit event repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.audit_log import AuditLog


class AuditRepository:
    """DataService-owned persistence operations for immutable audit events."""

    def __init__(self, session: AsyncSession, *, model: Any | None = None) -> None:
        self.session = session
        self.model = model or AuditLog

    def create(self, values: dict[str, Any]) -> Any:
        entry = self.model(**values)
        self.session.add(entry)
        return entry

    async def query(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Any]:
        stmt = select(self.model).order_by(self.model.created_at.desc())
        if workspace_id is not None:
            stmt = stmt.where(self.model.workspace_id == workspace_id)
        if user_id is not None:
            stmt = stmt.where(self.model.user_id == user_id)
        if since is not None:
            stmt = stmt.where(self.model.created_at >= since)
        result = await self.session.execute(stmt.limit(limit))
        return list(result.scalars().all())
