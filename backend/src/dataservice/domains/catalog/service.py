"""Canonical MissionPolicy and WorkerSkill catalog service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.mission_policy import MissionPolicy, WorkerSkill
from src.contracts.stage_acceptance import StageAcceptanceContract
from src.database.models.mission_catalog import MissionPolicyRecord, WorkerSkillRecord
from src.dataservice.domains.catalog.repository import MissionCatalogRepository


class MissionCatalogService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = MissionCatalogRepository(session)

    async def list_policies(self, *, workspace_type: str | None = None, enabled_only: bool = False) -> list[MissionPolicyRecord]:
        return await self.repository.list_policies(workspace_type=workspace_type, enabled_only=enabled_only)

    async def get_policy(self, *, policy_id: str, workspace_type: str) -> MissionPolicyRecord | None:
        return await self.repository.get_policy(policy_id=policy_id, workspace_type=workspace_type)

    async def list_skills(self, *, enabled_only: bool = False) -> list[WorkerSkillRecord]:
        return await self.repository.list_skills(enabled_only=enabled_only)

    async def get_skill(self, skill_id: str) -> WorkerSkillRecord | None:
        return await self.repository.get_skill(skill_id)

    async def has_policies(self) -> bool:
        return bool(await self.list_policies())

    async def has_skills(self) -> bool:
        return bool(await self.list_skills())

    async def load_policies(self, items: list[dict[str, Any]], *, overwrite: bool) -> int:
        self._reject_duplicate_identities((str(item["data"].get("workspace_type")), str(item["data"].get("id"))) for item in items)
        if overwrite:
            await self.repository.clear_policies()
        loaded = 0
        for item in items:
            stored_data = dict(item["data"])
            policy_data = dict(stored_data)
            resolved = policy_data.pop("resolved_stage_contracts", [])
            policy_data.pop("content_hash", None)
            policy = MissionPolicy.model_validate(policy_data)
            content_hash = self._validated_content_hash(stored_data, policy.immutable_ref().sha256)
            for raw_contract in resolved:
                contract = StageAcceptanceContract.model_validate(raw_contract)
                if contract.mission_policy_id != policy.id:
                    raise ValueError("resolved stage contract belongs to another policy")
            workspace_type = policy.workspace_type
            existing = await self.repository.get_policy(policy_id=policy.id, workspace_type=workspace_type)
            if existing is not None and not overwrite and existing.content_hash == content_hash:
                existing.source_path = item.get("source_path")
                continue
            record = existing or MissionPolicyRecord(id=policy.id, workspace_type=workspace_type)
            record.schema_version = policy.schema_version
            record.enabled = policy.enabled
            record.policy_json = stored_data
            record.content_hash = content_hash
            record.source_path = item.get("source_path")
            self.session.add(record)
            loaded += 1
        await self._finish()
        return loaded

    async def load_skills(self, items: list[dict[str, Any]], *, overwrite: bool) -> int:
        self._reject_duplicate_identities((str(item["data"].get("id")),) for item in items)
        if overwrite:
            await self.repository.clear_skills()
        loaded = 0
        for item in items:
            stored_data = dict(item["data"])
            skill_data = dict(stored_data)
            skill_data.pop("content_hash", None)
            skill = WorkerSkill.model_validate(skill_data)
            content_hash = self._validated_content_hash(stored_data, skill.immutable_ref().sha256)
            existing = await self.repository.get_skill(skill.id)
            if existing is not None and not overwrite and existing.content_hash == content_hash:
                existing.source_path = item.get("source_path")
                continue
            record = existing or WorkerSkillRecord(id=skill.id)
            record.schema_version = skill.schema_version
            record.enabled = skill.enabled
            record.skill_json = stored_data
            record.content_hash = content_hash
            record.source_path = item.get("source_path")
            self.session.add(record)
            loaded += 1
        await self._finish()
        return loaded

    async def _finish(self) -> None:
        await self.session.flush()
        if self.autocommit:
            await self.session.commit()

    @staticmethod
    def _validated_content_hash(data: dict[str, Any], expected: str) -> str:
        content_hash = str(data.get("content_hash") or "")
        if content_hash != expected:
            raise ValueError("catalog content_hash does not match canonical contract")
        return content_hash

    @staticmethod
    def _reject_duplicate_identities(identities) -> None:
        values = tuple(identities)
        if len(values) != len(set(values)):
            raise ValueError("catalog seed payload contains duplicate identities")
