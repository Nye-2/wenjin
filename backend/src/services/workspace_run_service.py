"""CRUD for WorkspaceRun (spec §6.2 B3 — full persistence + soft-delete)."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_run import WorkspaceRunRow


class WorkspaceRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_run(
        self, *, run_id: str, workspace_id: str, thread_id: str, title: str, started_at: datetime
    ) -> str:
        """Create a workspace_run row with an *externally-supplied* run_id.

        The caller MUST pass `subagent.execution_id` as run_id so the
        persisted row matches the id used by the SSE event stream and the
        frontend `Run.id`. (Cross-plan invariant — see Plan 2 Task 3.)
        """
        row = WorkspaceRunRow(
            id=run_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            title=title,
            started_at=started_at,
            status="running",
            created_at=datetime.now(UTC),
        )
        self._s.add(row)
        await self._s.flush()
        return row.id

    async def complete_run(
        self, run_id: str, *, result_card: dict[str, Any], stats: dict[str, Any]
    ) -> None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None or row.deleted_at is not None:
            return
        row.status = "completed"
        row.completed_at = datetime.now(UTC)
        row.result_card = result_card
        row.stats = stats
        await self._s.flush()

    async def get_run(self, run_id: str) -> WorkspaceRunRow | None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None or row.deleted_at is not None:
            return None
        return row

    async def delete_run(self, run_id: str) -> None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None:
            return
        row.deleted_at = datetime.now(UTC)
        await self._s.flush()

    async def list_runs(
        self, *, thread_id: str, include_deleted: bool = False
    ) -> list[WorkspaceRunRow]:
        stmt = select(WorkspaceRunRow).where(WorkspaceRunRow.thread_id == thread_id)
        if not include_deleted:
            stmt = stmt.where(WorkspaceRunRow.deleted_at.is_(None))
        stmt = stmt.order_by(WorkspaceRunRow.started_at)
        result = await self._s.execute(stmt)
        return list(result.scalars())
