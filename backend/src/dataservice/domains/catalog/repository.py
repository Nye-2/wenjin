"""Persistence for the Mission policy catalog."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.mission_catalog import MissionPolicyRecord, WorkerSkillRecord


class MissionCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_policies(self, *, workspace_type: str | None = None, enabled_only: bool = False) -> list[MissionPolicyRecord]:
        stmt = select(MissionPolicyRecord)
        if workspace_type:
            stmt = stmt.where(MissionPolicyRecord.workspace_type == workspace_type)
        if enabled_only:
            stmt = stmt.where(MissionPolicyRecord.enabled.is_(True))
        result = await self.session.execute(stmt.order_by(MissionPolicyRecord.workspace_type, MissionPolicyRecord.id))
        return list(result.scalars())

    async def get_policy(self, *, policy_id: str, workspace_type: str) -> MissionPolicyRecord | None:
        return await self.session.get(MissionPolicyRecord, (policy_id, workspace_type))

    async def list_skills(self, *, enabled_only: bool = False) -> list[WorkerSkillRecord]:
        stmt = select(WorkerSkillRecord)
        if enabled_only:
            stmt = stmt.where(WorkerSkillRecord.enabled.is_(True))
        result = await self.session.execute(stmt.order_by(WorkerSkillRecord.id))
        return list(result.scalars())

    async def get_skill(self, skill_id: str) -> WorkerSkillRecord | None:
        return await self.session.get(WorkerSkillRecord, skill_id)

    async def clear_policies(self) -> None:
        await self.session.execute(delete(MissionPolicyRecord))

    async def clear_skills(self) -> None:
        await self.session.execute(delete(WorkerSkillRecord))
