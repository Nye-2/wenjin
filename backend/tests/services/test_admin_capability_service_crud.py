"""Tests for AdminCapabilityService CRUD operations.

Uses SQLite-compatible test models for Capability round-trip tests.
AdminLog is monkeypatched to a lightweight mock model.
"""

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

from src.services.admin_capability_service import AdminCapabilityService

SAMPLE_YAML = """
id: test_cap
workspace_type: thesis
display_name: Test Capability
intent_description: for testing
brief_schema:
  type: object
graph_template:
  phases:
    - name: phase1
      tasks:
        - name: t1
          subagent_type: react
ui_meta:
  icon: search
  color: purple
"""


# ---------------------------------------------------------------------------
# Minimal SQLite models
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _TestCapability(_Base):
    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_phrases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_decisions: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    brief_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    graph_template: Mapped[dict] = mapped_column(JSON, nullable=False)
    ui_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runtime: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dashboard_meta: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class _TestAdminLog(_Base):
    """Lightweight admin_log stand-in for SQLite tests."""

    __tablename__ = "admin_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    admin_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="capability"
    )
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def crud_db():
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
    import src.services.admin_capability_service as mod

    monkeypatch.setattr(mod, "Capability", _TestCapability)
    monkeypatch.setattr(mod, "AdminLog", _TestAdminLog)


@pytest_asyncio.fixture
async def service(crud_db):
    bus = AsyncMock()
    # Stub out the CrossRefValidator so we don't need the real registry
    fake_validator = MagicMock()
    fake_validator.validate_capability = AsyncMock(return_value=[])
    svc = AdminCapabilityService(db=crud_db, event_bus=bus)
    svc.validator = fake_validator
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_capability(service):
    cap = await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    assert cap.id == "test_cap"
    assert cap.workspace_type == "thesis"
    assert cap.ui_meta["icon"] == "search"
    service.event_bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": "test_cap", "workspace_type": "thesis"},
    )


@pytest.mark.asyncio
async def test_create_with_invalid_yaml_raises(service):
    with pytest.raises(ValueError, match="yaml"):
        await service.create(yaml_text="!!!not yaml{{{", admin_id="admin-uuid")
    service.event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_get_returns_created_capability(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.get("test_cap", "thesis")
    assert cap is not None
    assert cap.display_name == "Test Capability"


@pytest.mark.asyncio
async def test_list_all_returns_capabilities(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    items = await service.list_all()
    assert len(items) == 1
    assert items[0].id == "test_cap"


@pytest.mark.asyncio
async def test_update_modifies_fields(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    updated_yaml = SAMPLE_YAML.replace("Test Capability", "Updated Name")
    cap = await service.update(
        capability_id="test_cap",
        workspace_type="thesis",
        yaml_text=updated_yaml,
        admin_id="admin-uuid",
    )
    assert cap.display_name == "Updated Name"


@pytest.mark.asyncio
async def test_update_rejects_id_mismatch(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    with pytest.raises(ValueError, match="must match"):
        await service.update(
            capability_id="wrong_id",
            workspace_type="thesis",
            yaml_text=SAMPLE_YAML,
            admin_id="admin-uuid",
        )


@pytest.mark.asyncio
async def test_delete_removes_capability(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    await service.delete(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    cap = await service.get("test_cap", "thesis")
    assert cap is None
    service.event_bus.publish.assert_awaited()


@pytest.mark.asyncio
async def test_toggle_flips_enabled(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.toggle(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    assert cap.enabled is False
    cap2 = await service.toggle(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    assert cap2.enabled is True


@pytest.mark.asyncio
async def test_validate_returns_errors_without_writing(service):
    bad_yaml = SAMPLE_YAML.replace(
        "subagent_type: react", "subagent_type: nonexistent"
    )
    # Stub the validator to return an error
    service.validator.validate_capability = AsyncMock(
        return_value=["subagent_type 'nonexistent' not in v2 subagent registry"]
    )
    errors = await service.validate(yaml_text=bad_yaml)
    assert any("nonexistent" in e for e in errors)
    service.event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_to_yaml_text_round_trips(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.get("test_cap", "thesis")
    yaml_text = service.to_yaml_text(cap)
    assert "test_cap" in yaml_text
    assert "thesis" in yaml_text
