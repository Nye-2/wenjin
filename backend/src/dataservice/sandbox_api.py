"""Public in-process sandbox API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactCreateCommand,
    SandboxArtifactProjection,
    SandboxEnvironmentCreateCommand,
    SandboxEnvironmentProjection,
    SandboxEnvironmentUpdateCommand,
    SandboxJobCreateCommand,
    SandboxJobProjection,
    SandboxJobUpdateCommand,
)
from src.dataservice.domains.sandbox.service import SandboxDataDomainService


class SandboxDataService:
    """Sandbox metadata API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = SandboxDataDomainService(session, autocommit=autocommit)

    async def create_environment(
        self,
        command: SandboxEnvironmentCreateCommand,
    ) -> SandboxEnvironmentProjection:
        return await self._domain.create_environment(command)

    async def get_or_create_environment(
        self,
        command: SandboxEnvironmentCreateCommand,
    ) -> SandboxEnvironmentProjection:
        return await self._domain.get_or_create_environment(command)

    async def get_environment(self, environment_id: str) -> SandboxEnvironmentProjection | None:
        return await self._domain.get_environment(environment_id)

    async def list_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SandboxEnvironmentProjection]:
        return await self._domain.list_environments(
            workspace_id=workspace_id,
            state=state,
            limit=limit,
        )

    async def update_environment(
        self,
        environment_id: str,
        command: SandboxEnvironmentUpdateCommand,
    ) -> SandboxEnvironmentProjection | None:
        return await self._domain.update_environment(environment_id, command)

    async def create_job(self, command: SandboxJobCreateCommand) -> SandboxJobProjection:
        return await self._domain.create_job(command)

    async def update_job(
        self,
        job_id: str,
        command: SandboxJobUpdateCommand,
    ) -> SandboxJobProjection | None:
        return await self._domain.update_job(job_id, command)

    async def list_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobProjection]:
        return await self._domain.list_jobs(
            workspace_id=workspace_id,
            sandbox_environment_id=sandbox_environment_id,
            execution_id=execution_id,
            status=status,
            limit=limit,
        )

    async def register_artifact(
        self,
        command: SandboxArtifactCreateCommand,
    ) -> SandboxArtifactProjection:
        return await self._domain.register_artifact(command)

    async def list_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactProjection]:
        return await self._domain.list_artifacts(
            workspace_id=workspace_id,
            sandbox_job_id=sandbox_job_id,
            materialization_status=materialization_status,
            limit=limit,
        )
