"""Phase 1 foundation integration test.

Verifies that the platform infrastructure layer + capability registry work
together without errors. Detailed business-logic correctness is covered by
per-task unit tests; this file is a smoke test for end-to-end wiring.

Spec: docs/superpowers/specs/2026-05-09-wenjin-workspace-rebuild-design.md
Plan: docs/superpowers/plans/2026-05-09-wenjin-workspace-rebuild.md Task 1.19
"""

from __future__ import annotations

import textwrap
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.database.conftest import (
    _Base,
    DbAuditLog,
    DbCapability,
)


# ---------------------------------------------------------------------------
# Local SQLite session fixture (bypasses integration/conftest.py's version,
# which uses a different schema that omits capabilities/audit_logs tables).
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session with the full database-contract schema."""
    engine = create_async_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event_bus_mock():
    """Return a lightweight mock EventBus that stores subscribe handlers."""
    bus = AsyncMock()
    bus._handlers: dict[str, list] = {}

    def _subscribe(channel, handler):
        bus._handlers.setdefault(channel, []).append(handler)

    bus.subscribe = _subscribe
    return bus


@asynccontextmanager
async def _wrap_session(session):
    """Expose an existing session as an async context manager."""
    yield session


def _session_factory(session):
    return lambda: _wrap_session(session)


_SEED_YAML = textwrap.dedent("""\
    id: deep_research
    workspace_type: thesis
    display_name: 深度文献调研
    description: 对某个主题做学术性的深度文献调研
    intent_description: 用户希望对某个主题做学术性的深度文献调研
    brief_schema:
      type: object
      required: [topic]
      properties:
        topic: {type: string}
    graph_template:
      phases:
        - name: discover
          tasks:
            - name: search
              subagent_type: searcher
    ui_meta:
      icon: search
      color: purple
      order: 0
""")


# ---------------------------------------------------------------------------
# Test 1: Capability load → resolve → cache → invalidate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capability_load_resolve_invalidate(db_session, tmp_path):
    """Seed YAML → loader writes DB → resolver caches → invalidate clears cache."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    (seed_dir / "deep_research.yaml").write_text(_SEED_YAML)

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        session=db_session,
        seed_dir=str(tmp_path / "capabilities"),
        model=DbCapability,
    )
    count = await loader.load_seeds_if_empty()
    assert count == 1, "Loader should have inserted exactly 1 capability"

    from src.services.capability_resolver import CapabilityResolver

    bus = _make_event_bus_mock()
    resolver = CapabilityResolver(
        session_factory=_session_factory(db_session),
        event_bus=bus,
        model=DbCapability,
    )

    # First resolve: DB hit, result cached
    cap = await resolver.resolve("deep_research", "thesis")
    assert cap.id == "deep_research"
    assert cap.workspace_type == "thesis"
    assert cap.display_name == "深度文献调研"
    assert ("deep_research", "thesis") in resolver._cache

    # Second resolve: cache hit — same object
    cap2 = await resolver.resolve("deep_research", "thesis")
    assert cap2 is cap

    # Trigger cache invalidation event
    handler = bus._handlers["capability.invalidated"][0]
    await handler({"capability_id": "deep_research", "workspace_type": "thesis"})
    assert ("deep_research", "thesis") not in resolver._cache

    # Re-resolve after invalidation still succeeds (re-queries DB)
    cap3 = await resolver.resolve("deep_research", "thesis")
    assert cap3.id == "deep_research"


# ---------------------------------------------------------------------------
# Test 2: QuotaService with mock Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_consume_atomic_with_mock_redis():
    """QuotaService.consume() raises QuotaExceeded when Lua returns -1."""
    from src.services.quota_service import QuotaExceeded, QuotaService

    redis = AsyncMock()
    # Lua script: first 3 consumes succeed, 4th is rejected (over limit)
    redis.eval.side_effect = [100_000, 200_000, 300_000, -1]

    qs = QuotaService(redis, daily_token_limit=300_000)
    assert await qs.consume("u1", kind="tokens_daily", amount=100_000) == 100_000
    assert await qs.consume("u1", kind="tokens_daily", amount=100_000) == 200_000
    assert await qs.consume("u1", kind="tokens_daily", amount=100_000) == 300_000

    with pytest.raises(QuotaExceeded):
        await qs.consume("u1", kind="tokens_daily", amount=100_000)

    assert redis.eval.call_count == 4


# ---------------------------------------------------------------------------
# Test 3: AuditService log + query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_and_query(db_session):
    """AuditService logs events and can filter by workspace_id."""
    from src.services.audit_service import AuditService

    svc = AuditService(
        session_factory=_session_factory(db_session),
        model=DbAuditLog,
    )

    ws_id = "ws-test-123"
    await svc.log("capability.resolved", workspace_id=ws_id, payload={"cap_id": "deep_research"})
    await svc.log("quota.consumed", workspace_id=ws_id, payload={"kind": "tokens_daily"})
    await svc.log("other.action", workspace_id="ws-other-456")

    # Query scoped to ws_id → 2 entries
    logs = await svc.query(workspace_id=ws_id)
    assert len(logs) == 2
    actions = {log.action for log in logs}
    assert actions == {"capability.resolved", "quota.consumed"}

    # Unfiltered → all 3
    all_logs = await svc.query()
    assert len(all_logs) == 3


# ---------------------------------------------------------------------------
# Test 4: EventBus publish/subscribe with mock Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_publish_subscribe_with_mock_redis():
    """EventBus.publish() calls redis.publish; local handlers receive events."""
    from src.services.event_bus import EventBus

    redis = AsyncMock()
    redis.publish.return_value = 1

    bus = EventBus(redis)
    received: list[dict] = []

    async def handler(event: dict) -> None:
        received.append(event)

    bus.subscribe("test.channel", handler)

    result = await bus.publish("test.channel", {"key": "value"})
    assert result == 1
    redis.publish.assert_called_once()
    assert redis.publish.call_args[0][0] == "test.channel"

    # Dispatch to local handler (simulating _listen)
    for h in bus._handlers.get("test.channel", []):
        await h({"key": "value"})

    assert received == [{"key": "value"}]


# ---------------------------------------------------------------------------
# Test 5: All 8 room services instantiate (wiring smoke test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_room_services_boot(db_session):
    """All 8 room services can be imported and instantiated without error."""
    from src.services.rooms.library_service import LibraryService
    from src.services.rooms.documents_service import DocumentsService
    from src.services.rooms.decisions_service import DecisionsService
    from src.services.rooms.memory_service import MemoryService
    from src.services.rooms.run_history_service import RunHistoryService
    from src.services.rooms.sandbox_service import SandboxService
    from src.services.rooms.workspace_tasks_service import WorkspaceTasksService
    from src.services.rooms.settings_service import WorkspaceSettingsService

    LibraryService(db_session)
    DocumentsService(db_session)
    DecisionsService(db_session)
    MemoryService(db_session)
    RunHistoryService(db_session)
    SandboxService(db_session)
    WorkspaceTasksService(db_session)
    WorkspaceSettingsService(db_session)
    # All 8 services booted without exception
