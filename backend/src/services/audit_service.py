"""Audit log service — best-effort event logging."""

from __future__ import annotations

import logging
from datetime import datetime

from src.dataservice.audit_api import AuditDataService

logger = logging.getLogger(__name__)


class AuditService:
    """Writes audit events to the audit_logs table.

    All methods are best-effort: failures are logged as warnings and never
    propagate to callers.

    Args:
        session_factory: Callable returning an async context manager that yields an AsyncSession.
        model: The ORM model class to use (defaults to production AuditLog).
    """

    def __init__(self, session_factory, model=None) -> None:
        self._session_factory = session_factory
        self._model = model

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
            async with self._session_factory() as session:
                await AuditDataService(session, model=self._model).log(
                    action=action,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    target_type=target_type,
                    target_id=target_id,
                    payload=payload,
                    ip=ip,
                    ua=ua,
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
        async with self._session_factory() as session:
            return await AuditDataService(session, model=self._model, autocommit=False).query(
                workspace_id=workspace_id,
                user_id=user_id,
                since=since,
                limit=limit,
            )
