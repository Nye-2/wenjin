"""Bootstrap admin user for Wenjin (问津).

This module creates the default admin account on first deployment.
It is designed to be idempotent - safe to run multiple times.

Environment variables:
    DATABASE_URL: PostgreSQL connection string (required)
    ADMIN_EMAIL: Admin email (default: admin@wenjin.ai)
    ADMIN_PASSWORD: Admin password (default: admin123)
    ADMIN_NAME: Admin display name (default: Admin)
"""

from __future__ import annotations

import asyncio
import os
from typing import get_args

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.contracts.mission_policy import MissionPolicy, WorkerSkill
from src.contracts.stage_acceptance import StageAcceptanceContract, WorkspaceType
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader

# Default admin credentials
DEFAULT_ADMIN_EMAIL = "admin@wenjin.ai"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_NAME = "Admin"
_MISSION_CATALOG_BOOTSTRAP_LOCK = 8_461_904_271


async def seed_mission_catalog(session: AsyncSession) -> tuple[int, int]:
    """Synchronize and validate the canonical Mission catalog atomically."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _MISSION_CATALOG_BOOTSTRAP_LOCK},
        )

    service = MissionCatalogService(session, autocommit=False)
    loaded_skills = await SkillLoader().sync_with_service(service)
    loaded_policies = await MissionPolicyLoader().sync_with_service(service)

    skills = {row.id: row for row in await service.list_skills(enabled_only=True)}
    for record in skills.values():
        raw_skill = dict(record.skill_json)
        embedded_hash = str(raw_skill.pop("content_hash", "") or "")
        skill = WorkerSkill.model_validate(raw_skill)
        if embedded_hash != record.content_hash or skill.immutable_ref().sha256 != record.content_hash:
            raise RuntimeError(f"WorkerSkill hash drift: {record.id}")
    policies = await service.list_policies(enabled_only=True)
    by_workspace: dict[str, list[object]] = {}
    for record in policies:
        stored_policy = dict(record.policy_json)
        raw_contracts = stored_policy.pop("resolved_stage_contracts", None)
        embedded_hash = str(stored_policy.pop("content_hash", "") or "")
        policy = MissionPolicy.model_validate(stored_policy)
        if embedded_hash != record.content_hash or policy.immutable_ref().sha256 != record.content_hash:
            raise RuntimeError(f"MissionPolicy hash drift: {record.id}")
        if not isinstance(raw_contracts, list):
            raise RuntimeError(f"MissionPolicy has no resolved stages: {record.id}")
        contracts = [StageAcceptanceContract.model_validate(item) for item in raw_contracts]
        expected_refs = {(item.contract_id, item.sha256) for item in policy.stage_contract_refs}
        actual_refs = {
            (item.contract_id, item.immutable_ref().sha256) for item in contracts
        }
        if expected_refs != actual_refs:
            raise RuntimeError(f"MissionPolicy stage hash drift: {record.id}")
        missing = set(policy.allowed_worker_skills) - skills.keys()
        if missing:
            raise RuntimeError(
                f"MissionPolicy {record.id} references unavailable WorkerSkill(s): "
                + ", ".join(sorted(missing))
            )
        by_workspace.setdefault(record.workspace_type, []).append(record)

    required_workspace_types = set(get_args(WorkspaceType))
    missing_workspaces = sorted(required_workspace_types - by_workspace.keys())
    if missing_workspaces:
        raise RuntimeError(
            "Mission catalog has no enabled policy for workspace type(s): "
            + ", ".join(missing_workspaces)
        )
    if not skills:
        raise RuntimeError("Mission catalog has no enabled WorkerSkill")
    await session.commit()
    return loaded_skills, loaded_policies


async def create_admin_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: str,
) -> bool:
    """Create admin user if not exists.

    Args:
        session: Database session
        email: Admin email (plain text, will be normalized)
        password: Admin password (plain text, will be hashed)
        name: Admin display name

    Returns:
        True if admin was created, False if already existed
    """
    # Import here to avoid circular imports
    from src.database import User
    from src.services.auth import hash_password

    # Check if admin already exists
    result = await session.execute(
        select(User).where(User.email == email.lower().strip())
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # Ensure existing user has admin privileges
        if not existing_user.is_superuser:
            existing_user.is_superuser = True
            await session.commit()
            print(f"[bootstrap-admin] User {email} promoted to admin")
        else:
            print(f"[bootstrap-admin] Admin user {email} already exists")
        return False

    # Create new admin user
    hashed_password = hash_password(password)

    admin = User(
        email=email.lower().strip(),
        name=name,
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=True,
        credits=10000,  # Grant generous credits to admin
        total_credits_earned=10000,
    )

    session.add(admin)
    await session.commit()

    print(f"[bootstrap-admin] Admin user created: {email}")
    return True


async def async_main() -> int:
    """Main async entry point."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[bootstrap-admin] ERROR: DATABASE_URL is required")
        return 1

    admin_email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    admin_password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    admin_name = os.getenv("ADMIN_NAME", DEFAULT_ADMIN_NAME)

    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(  # type: ignore[call-overload]
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session() as session:
            await create_admin_user(
                session=session,
                email=admin_email,
                password=admin_password,
                name=admin_name,
            )

            # Seed pricing policies before the admin-managed model catalog.
            from src.dataservice_app.bootstrap_model_catalog import seed_model_catalog_from_env

            loaded_models = await seed_model_catalog_from_env(
                session,
                admin_id=admin_email,
            )
            if loaded_models:
                print(f"[bootstrap-admin] Seeded {loaded_models} model catalog record(s)")

            loaded_skills, loaded_policies = await seed_mission_catalog(session)
            print(
                "[bootstrap-admin] Mission catalog ready: "
                f"{loaded_skills} WorkerSkill update(s), "
                f"{loaded_policies} MissionPolicy update(s)"
            )
        return 0
    except Exception as e:
        print(f"[bootstrap-admin] ERROR: {e}")
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    """Main entry point for docker-compose."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
