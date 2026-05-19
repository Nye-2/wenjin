"""Service layer for run history."""

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.run_history import RunHistory

logger = logging.getLogger(__name__)


class RunHistoryService:
    """CRUD for run_history."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[RunHistory] = RunHistory,
    ) -> None:
        self.db = db
        self._model = model

    async def record(
        self,
        workspace_id: str,
        execution_id: str,
        capability_id: str,
        title: str,
        summary: str,
        status: str,
        duration_seconds: int,
        token_usage: dict[str, Any] | None = None,
        artifact_count: int = 0,
    ) -> RunHistory:
        """Record a completed execution run."""
        existing = await self._get_by_execution_id(execution_id)
        if existing is not None:
            self._apply_record_fields(
                existing,
                workspace_id=workspace_id,
                capability_id=capability_id,
                title=title,
                summary=summary,
                status=status,
                duration_seconds=duration_seconds,
                token_usage=token_usage,
                artifact_count=artifact_count,
            )
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        row = self._model(
            id=str(uuid4()),
            workspace_id=workspace_id,
            execution_id=execution_id,
            capability_id=capability_id,
            title=title,
            summary=summary,
            status=status,
            duration_seconds=duration_seconds,
            token_usage=token_usage,
            artifact_count=artifact_count,
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self._get_by_execution_id(execution_id)
            if existing is None:
                raise
            self._apply_record_fields(
                existing,
                workspace_id=workspace_id,
                capability_id=capability_id,
                title=title,
                summary=summary,
                status=status,
                duration_seconds=duration_seconds,
                token_usage=token_usage,
                artifact_count=artifact_count,
            )
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        await self.db.refresh(row)
        return row

    async def _get_by_execution_id(self, execution_id: str) -> RunHistory | None:
        result = await self.db.execute(
            select(self._model).where(self._model.execution_id == execution_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_record_fields(
        row: RunHistory,
        *,
        workspace_id: str,
        capability_id: str,
        title: str,
        summary: str,
        status: str,
        duration_seconds: int,
        token_usage: dict[str, Any] | None,
        artifact_count: int,
    ) -> None:
        row.workspace_id = workspace_id
        row.capability_id = capability_id
        row.title = title
        row.summary = summary
        row.status = status
        row.duration_seconds = duration_seconds
        row.token_usage = token_usage
        row.artifact_count = artifact_count

    async def list(
        self, workspace_id: str, limit: int = 50
    ) -> list[RunHistory]:
        """List non-deleted run history entries, ordered by created_at DESC."""
        result = await self.db.execute(
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
            .order_by(self._model.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(
        self, workspace_id: str, run_id: str
    ) -> RunHistory | None:
        """Get a single run history entry."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.id == run_id,
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
