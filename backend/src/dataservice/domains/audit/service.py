"""Audit event command/query service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.audit.repository import AuditRepository


class DataServiceAuditService:
    """DataService-owned audit event lifecycle operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        model: Any | None = None,
        autocommit: bool = True,
    ) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = AuditRepository(session, model=model)

    async def log(
        self,
        *,
        action: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
        ip: str | None = None,
        ua: str | None = None,
    ) -> Any:
        entry = self.repository.create(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "payload": payload,
                "ip_address": ip,
                "user_agent": ua,
            }
        )
        await self._finish()
        return entry

    async def query(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self.repository.query(
            workspace_id=workspace_id,
            user_id=user_id,
            since=since,
            limit=limit,
        )

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
