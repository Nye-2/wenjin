"""Sandbox aggregate repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.sandbox.models import (
    SandboxArtifactRecord,
    SandboxEnvironmentRecord,
    SandboxJobRecord,
)


class SandboxRepository:
    """Persistence operations for sandbox environments, jobs, and artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_environment(self, values: dict[str, Any]) -> SandboxEnvironmentRecord:
        record = SandboxEnvironmentRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_environment(self, environment_id: str) -> SandboxEnvironmentRecord | None:
        result = await self.session.execute(
            select(SandboxEnvironmentRecord).where(SandboxEnvironmentRecord.id == environment_id)
        )
        return result.scalar_one_or_none()

    async def get_active_environment(self, workspace_id: str) -> SandboxEnvironmentRecord | None:
        result = await self.session.execute(
            select(SandboxEnvironmentRecord)
            .where(
                SandboxEnvironmentRecord.workspace_id == workspace_id,
                SandboxEnvironmentRecord.state == "active",
            )
            .order_by(SandboxEnvironmentRecord.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SandboxEnvironmentRecord]:
        query = (
            select(SandboxEnvironmentRecord)
            .where(SandboxEnvironmentRecord.workspace_id == workspace_id)
            .order_by(SandboxEnvironmentRecord.updated_at.desc())
            .limit(limit)
        )
        if state is not None:
            query = query.where(SandboxEnvironmentRecord.state == state)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def create_job(self, values: dict[str, Any]) -> SandboxJobRecord:
        record = SandboxJobRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_job(self, job_id: str) -> SandboxJobRecord | None:
        result = await self.session.execute(
            select(SandboxJobRecord).where(SandboxJobRecord.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobRecord]:
        query = (
            select(SandboxJobRecord)
            .where(SandboxJobRecord.workspace_id == workspace_id)
            .order_by(SandboxJobRecord.created_at.desc())
            .limit(limit)
        )
        if sandbox_environment_id is not None:
            query = query.where(SandboxJobRecord.sandbox_environment_id == sandbox_environment_id)
        if execution_id is not None:
            query = query.where(SandboxJobRecord.execution_id == execution_id)
        if status is not None:
            query = query.where(SandboxJobRecord.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def create_artifact(self, values: dict[str, Any]) -> SandboxArtifactRecord:
        record = SandboxArtifactRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_artifact(self, artifact_id: str) -> SandboxArtifactRecord | None:
        result = await self.session.execute(
            select(SandboxArtifactRecord).where(SandboxArtifactRecord.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def list_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactRecord]:
        query = (
            select(SandboxArtifactRecord)
            .where(SandboxArtifactRecord.workspace_id == workspace_id)
            .order_by(SandboxArtifactRecord.created_at.desc())
            .limit(limit)
        )
        if sandbox_job_id is not None:
            query = query.where(SandboxArtifactRecord.sandbox_job_id == sandbox_job_id)
        if materialization_status is not None:
            query = query.where(SandboxArtifactRecord.materialization_status == materialization_status)
        result = await self.session.execute(query)
        return list(result.scalars().all())
