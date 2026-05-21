"""Catalog aggregate repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.database.models.admin_log import AdminLog
from src.database.models.capability_skill import CapabilitySkill
from src.database.models.user import User
from src.dataservice.domains.catalog.models import CapabilityDefinition, CapabilitySeedRevision


class CatalogRepository:
    """Persistence operations for capability catalog rows."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        admin_log_model: Any | None = None,
    ) -> None:
        self.session = session
        self.admin_log_model = admin_log_model or AdminLog

    async def has_capabilities(self) -> bool:
        return (await self.session.execute(select(CapabilityDefinition).limit(1))).first() is not None

    async def has_skills(self) -> bool:
        return (await self.session.execute(select(CapabilitySkill).limit(1))).first() is not None

    async def list_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[CapabilityDefinition]:
        query = select(CapabilityDefinition)
        if workspace_type:
            query = query.where(CapabilityDefinition.workspace_type == workspace_type)
        if enabled_only:
            query = query.where(CapabilityDefinition.enabled.is_(True))
        result = await self.session.execute(
            query.order_by(CapabilityDefinition.workspace_type, CapabilityDefinition.id)
        )
        return list(result.scalars().all())

    async def get_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = False,
    ) -> CapabilityDefinition | None:
        query = select(CapabilityDefinition).where(
            CapabilityDefinition.id == capability_id,
            CapabilityDefinition.workspace_type == workspace_type,
        )
        if enabled_only:
            query = query.where(CapabilityDefinition.enabled.is_(True))
        result = await self.session.execute(query)
        if hasattr(result, "scalar_one_or_none"):
            return result.scalar_one_or_none()
        return result.scalars().first()

    async def upsert_capability(self, values: dict[str, Any]) -> CapabilityDefinition:
        record = await self.get_capability(
            capability_id=str(values["id"]),
            workspace_type=str(values["workspace_type"]),
        )
        if record is None:
            record = CapabilityDefinition(**values)
            self.session.add(record)
            return record
        for key, value in values.items():
            setattr(record, key, value)
        return record

    async def delete_all_capabilities(self) -> None:
        await self.session.execute(delete(CapabilityDefinition))

    async def delete_capability(self, *, capability_id: str, workspace_type: str) -> bool:
        result = await self.session.execute(
            delete(CapabilityDefinition).where(
                CapabilityDefinition.id == capability_id,
                CapabilityDefinition.workspace_type == workspace_type,
            )
        )
        return bool(result.rowcount)

    async def list_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkill]:
        query = select(CapabilitySkill)
        if enabled_only:
            query = query.where(CapabilitySkill.enabled.is_(True))
        result = await self.session.execute(query.order_by(CapabilitySkill.id))
        return list(result.scalars().all())

    async def get_skill(self, skill_id: str, *, enabled_only: bool = False) -> CapabilitySkill | None:
        query = select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
        if enabled_only:
            query = query.where(CapabilitySkill.enabled.is_(True))
        return (await self.session.execute(query)).scalar_one_or_none()

    async def upsert_skill(self, values: dict[str, Any]) -> CapabilitySkill:
        record = await self.get_skill(str(values["id"]))
        if record is None:
            record = CapabilitySkill(**values)
            self.session.add(record)
            return record
        for key, value in values.items():
            setattr(record, key, value)
        return record

    async def delete_all_skills(self) -> None:
        await self.session.execute(delete(CapabilitySkill))

    async def delete_skill(self, skill_id: str) -> bool:
        result = await self.session.execute(delete(CapabilitySkill).where(CapabilitySkill.id == skill_id))
        return bool(result.rowcount)

    async def latest_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
    ) -> CapabilitySeedRevision | None:
        result = await self.session.execute(
            select(CapabilitySeedRevision)
            .where(
                CapabilitySeedRevision.catalog_kind == catalog_kind,
                CapabilitySeedRevision.seed_root == seed_root,
            )
            .order_by(CapabilitySeedRevision.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def create_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
        loaded_count: int,
        metadata_json: dict[str, Any],
    ) -> CapabilitySeedRevision:
        revision = CapabilitySeedRevision(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
            loaded_count=loaded_count,
            metadata_json=metadata_json,
        )
        self.session.add(revision)
        return revision

    def create_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        target_user_id: str | None,
        details: dict[str, Any],
        target_type: str = "user",
        ip_address: str | None = None,
    ) -> Any:
        values = {
            "action": action,
            "admin_id": admin_id,
            "target_type": target_type,
            "target_user_id": target_user_id,
            "details": details,
            "ip_address": ip_address,
        }
        record = self.admin_log_model(
            **{
                key: value
                for key, value in values.items()
                if hasattr(self.admin_log_model, key)
            }
        )
        self.session.add(record)
        return record

    async def list_admin_logs(
        self,
        *,
        action: str | None = None,
        target_user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Any], int]:
        admin_alias = aliased(User)
        target_alias = aliased(User)
        conditions = []
        if action:
            conditions.append(self.admin_log_model.action == action)
        if target_user_id:
            conditions.append(self.admin_log_model.target_user_id == target_user_id)

        filtered_logs = select(self.admin_log_model)
        if conditions:
            filtered_logs = filtered_logs.where(*conditions)

        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(filtered_logs.subquery())
                )
            ).scalar()
            or 0
        )
        rows = await self.session.execute(
            select(
                self.admin_log_model,
                admin_alias.email,
                admin_alias.name,
                target_alias.email,
                target_alias.name,
            )
            .join(admin_alias, self.admin_log_model.admin_id == admin_alias.id)
            .outerjoin(target_alias, self.admin_log_model.target_user_id == target_alias.id)
            .where(*conditions)
            .order_by(desc(self.admin_log_model.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(rows.all()), total
