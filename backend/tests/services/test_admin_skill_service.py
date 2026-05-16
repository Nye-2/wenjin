"""Tests for AdminSkillService CRUD."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from src.services.admin_skill_service import AdminSkillService

SAMPLE_SKILL_YAML = """
id: test-skill
display_name: Test Skill
description: Test
subagent_type: react
prompt: |
  You are a test agent.
allowed_tools: []
resources: []
config: {}
"""


# ---------------------------------------------------------------------------
# Minimal SQLite models
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _TestCapabilitySkill(_Base):
    __tablename__ = "capability_skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subagent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    allowed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class _TestAdminLog(_Base):
    __tablename__ = "admin_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    admin_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="skill"
    )
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def skill_db():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _patch_models(monkeypatch):
    """Replace the real ORM models with our SQLite-compatible ones."""
    import src.services.admin_skill_service as mod

    monkeypatch.setattr(mod, "CapabilitySkill", _TestCapabilitySkill)
    monkeypatch.setattr(mod, "AdminLog", _TestAdminLog)


@pytest_asyncio.fixture
async def service(skill_db):
    fake_validator = MagicMock()
    fake_validator.validate_skill = AsyncMock(return_value=[])
    svc = AdminSkillService(db=skill_db)
    svc.validator = fake_validator
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_persists(service):
    skill = await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    assert skill.id == "test-skill"
    assert skill.subagent_type == "react"


@pytest.mark.asyncio
async def test_invalid_subagent_type_fails(service):
    service.validator.validate_skill = AsyncMock(
        return_value=["subagent_type 'bogus_type' not in v2 subagent registry"]
    )
    bad = SAMPLE_SKILL_YAML.replace("subagent_type: react", "subagent_type: bogus_type")
    with pytest.raises(ValueError, match="bogus_type"):
        await service.create(yaml_text=bad, admin_id="admin-uuid")


@pytest.mark.asyncio
async def test_get_returns_created_skill(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.get("test-skill")
    assert skill is not None
    assert skill.display_name == "Test Skill"


@pytest.mark.asyncio
async def test_list_all_returns_skills(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    items = await service.list_all()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_update_modifies_fields(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    updated = SAMPLE_SKILL_YAML.replace("Test Skill", "Updated Skill")
    skill = await service.update(
        skill_id="test-skill", yaml_text=updated, admin_id="admin-uuid"
    )
    assert skill.display_name == "Updated Skill"


@pytest.mark.asyncio
async def test_update_rejects_id_mismatch(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    with pytest.raises(ValueError, match="must match"):
        await service.update(
            skill_id="wrong-id", yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid"
        )


@pytest.mark.asyncio
async def test_delete_removes_skill(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    await service.delete(skill_id="test-skill", admin_id="admin-uuid")
    skill = await service.get("test-skill")
    assert skill is None


@pytest.mark.asyncio
async def test_toggle_flips_enabled(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.toggle(skill_id="test-skill", admin_id="admin-uuid")
    assert skill.enabled is False
    skill2 = await service.toggle(skill_id="test-skill", admin_id="admin-uuid")
    assert skill2.enabled is True


@pytest.mark.asyncio
async def test_to_yaml_text_round_trips(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.get("test-skill")
    yaml_text = service.to_yaml_text(skill)
    assert "test-skill" in yaml_text
    assert "react" in yaml_text
