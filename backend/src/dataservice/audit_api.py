"""Public in-process audit API for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.audit.service import DataServiceAuditService


class AuditDataService:
    """Audit API exposed by DataService to runtime modules."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        model: Any | None = None,
        autocommit: bool = True,
    ) -> None:
        self._domain = DataServiceAuditService(
            session,
            model=model,
            autocommit=autocommit,
        )

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
        return await self._domain.log(
            action=action,
            user_id=user_id,
            workspace_id=workspace_id,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            ip=ip,
            ua=ua,
        )

    async def query(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._domain.query(
            workspace_id=workspace_id,
            user_id=user_id,
            since=since,
            limit=limit,
        )
