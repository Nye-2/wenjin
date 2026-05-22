"""Audit log service — best-effort event logging."""

from __future__ import annotations

import logging
from datetime import datetime

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.audit import AuditLogCreatePayload
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)


class AuditService:
    """Writes audit events to the audit_logs table.

    All methods are best-effort: failures are logged as warnings and never
    propagate to callers.

    Args:
        session_factory: Callable returning an async context manager that yields an AsyncSession.
        dataservice: Optional DataService client override for tests.
    """

    def __init__(
        self,
        session_factory,
        model=None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._model = model
        self._dataservice = dataservice

    async def log(
        self,
        action: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        payload: dict | None = None,
        ip: str | None = None,
        ua: str | None = None,
    ) -> None:
        """Record an audit event. Never raises."""
        try:
            if self._dataservice is not None:
                await self._dataservice.create_audit_log(
                    AuditLogCreatePayload(
                        action=action,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        target_type=target_type,
                        target_id=target_id,
                        payload=payload or {},
                        ip=ip,
                        ua=ua,
                    )
                )
                return
            async with dataservice_client() as client:
                await client.create_audit_log(
                    AuditLogCreatePayload(
                        action=action,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        target_type=target_type,
                        target_id=target_id,
                        payload=payload or {},
                        ip=ip,
                        ua=ua,
                    )
                )
        except Exception:
            logger.warning("Failed to write audit log for action=%s", action, exc_info=True)

    async def query(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list:
        """Query audit logs, ordered by created_at DESC."""
        if self._dataservice is not None:
            return await self._dataservice.query_audit_logs(
                workspace_id=workspace_id,
                user_id=user_id,
                since=since,
                limit=limit,
            )
        async with dataservice_client() as client:
            return await client.query_audit_logs(
                workspace_id=workspace_id,
                user_id=user_id,
                since=since,
                limit=limit,
            )
