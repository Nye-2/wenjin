"""Audit log service — best-effort event logging."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

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
        if model is None:
            from src.database.models.audit_log import AuditLog
            self._model = AuditLog
        else:
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
                entry = self._model(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    payload=payload,
                    ip_address=ip,
                    user_agent=ua,
                )
                session.add(entry)
                await session.commit()
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
            stmt = select(self._model).order_by(self._model.created_at.desc())
            if workspace_id is not None:
                stmt = stmt.where(self._model.workspace_id == workspace_id)
            if user_id is not None:
                stmt = stmt.where(self._model.user_id == user_id)
            if since is not None:
                stmt = stmt.where(self._model.created_at >= since)
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
