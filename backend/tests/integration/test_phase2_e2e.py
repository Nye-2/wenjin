"""Phase 2 end-to-end integration test.

Verifies: capability seed → CapabilityResolver → LeadAgentRuntime → ExecutionEngineV2
→ ExecutionCommitService → rooms populated.

This is a smoke test for Phase 2 wiring, not detailed correctness — per-task tests
already cover business logic.

Spec: docs/superpowers/specs/2026-05-09-wenjin-workspace-rebuild-design.md
Plan: docs/superpowers/plans/2026-05-09-wenjin-workspace-rebuild.md Task 2.14
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.subagents.v2.types  # noqa: F401 — populates REGISTRY with 5 V1 types
from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import (
    LibraryItemData,
    LibraryItemOutput,
    TaskReport,
)
from src.services.capability_loader import CapabilityLoader
from tests.database.conftest import _Base, DbCapability


# ---------------------------------------------------------------------------
# Local SQLite session fixture (bypasses integration/conftest.py schema,
# which omits the capabilities table used here).
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
# Helper: wrap a session as a callable async-context-manager session factory
# (matches CapabilityResolver constructor expectation)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _wrap_session(session: AsyncSession):
    yield session


def _session_factory(session: AsyncSession):
    return lambda: _wrap_session(session)


def _make_event_bus_mock():
    """Return a lightweight mock EventBus that stores subscribe handlers."""
    bus = AsyncMock()
    bus._handlers: dict[str, list] = {}

    def _subscribe(channel, handler):
        bus._handlers.setdefault(channel, []).append(handler)

    bus.subscribe = _subscribe
    return bus


# ---------------------------------------------------------------------------
# Test 1: Seeded capability → resolver → runtime completes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_agent_runtime_with_seeded_capability_completes(db_session):
    """Load seed → resolver finds it → runtime invokes graph → completes."""
    # 1. Load seeds using DbCapability mock model (not production Capability)
    loader = CapabilityLoader(session=db_session, model=DbCapability)
    n = await loader.load_seeds_if_empty()
    assert n >= 5, f"Expected at least 5 seeds, got {n}"

    # 2. Create resolver bound to the test session
    from src.services.capability_resolver import CapabilityResolver

    bus = _make_event_bus_mock()
    resolver = CapabilityResolver(
        session_factory=_session_factory(db_session),
        event_bus=bus,
        model=DbCapability,
    )

    # 3. Build runtime with a mock publish_event
    publish_mock = AsyncMock()
    from src.agents.lead_agent.v2.runtime import LeadAgentRuntime

    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish_mock,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    # 4. Invoke with a TaskBrief for the simplest capability (outline_generate)
    brief = TaskBrief(
        capability_id="outline_generate",
        brief={"topic": "Conditional GAN for image synthesis"},
        raw_message="帮我做个论文大纲",
        decisions={},
        workspace_id="ws-test",
    )
    report = await runtime.run_session(execution_id="e-1", brief=brief)

    # 5. Verify report
    assert report.status == "completed"
    assert report.execution_id == "e-1"
    assert report.duration_seconds >= 0

    # Verify the two key events were published
    event_names = [c.args[1] for c in publish_mock.call_args_list]
    assert "execution.graph_structure" in event_names, (
        f"expected execution.graph_structure in {event_names}"
    )
    assert "execution.completed" in event_names, (
        f"expected execution.completed in {event_names}"
    )


# ---------------------------------------------------------------------------
# Test 2: ExecutionEngineV2 wraps runtime, persists status + writes run_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_v2_full_pipeline_with_run_history():
    """ExecutionEngineV2 wraps runtime, marks status + writes run_history."""
    from src.execution.engine import ExecutionEngineV2

    runtime = AsyncMock()
    runtime.run_session.return_value = TaskReport(
        execution_id="e-1",
        capability_id="outline_generate",
        status="completed",
        duration_seconds=2,
        narrative="完成大纲",
        outputs=[],
        errors=[],
    )

    execution_service = AsyncMock()
    execution_service.get_by_id.return_value = MagicMock(
        params={
            "brief": {
                "capability_id": "outline_generate",
                "brief": {"topic": "Conditional GAN"},
                "raw_message": "帮我做个大纲",
                "decisions": {},
                "workspace_id": "ws-1",
            }
        },
        workspace_id="ws-1",
        feature_id="outline_generate",
    )

    run_history = AsyncMock()

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_service,
        run_history_service=run_history,
    )

    await engine.run("e-1")

    # Runtime was called with the brief
    runtime.run_session.assert_awaited_once()
    # Status transitions: pending → running → completed
    execution_service.start_execution.assert_awaited_once_with("e-1")
    execution_service.complete_execution.assert_awaited_once()
    # Run history recorded
    run_history.record.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 3: ExecutionCommitService writes rooms after E2E
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_after_e2e_writes_rooms():
    """ExecutionCommitService commits library output + always records run_history."""
    from src.services.execution_commit_service import ExecutionCommitService

    # Build a TaskReport with one library_item output
    report = TaskReport(
        execution_id="e-1",
        capability_id="deep_research",
        status="completed",
        duration_seconds=10,
        narrative="完成深度文献调研",
        outputs=[
            LibraryItemOutput(
                id="out-1",
                kind="library_item",
                preview="Goodfellow GANs",
                default_checked=True,
                data=LibraryItemData(
                    title="Generative Adversarial Networks",
                    authors=["Goodfellow"],
                    year=2014,
                    doi="10.1145/3422622",
                    url=None,
                    abstract=None,
                    metadata={},
                ),
            ),
        ],
    )

    execution_service = AsyncMock()
    execution_service.get_by_id.return_value = SimpleNamespace(
        id="e-1",
        result={"task_report": report.model_dump(mode="json")},
        workspace_id="ws-1",
        user_id="u-1",
        feature_id="deep_research",
        status="completed",
    )

    library = MagicMock()
    library.add = AsyncMock(return_value=SimpleNamespace(id="lib-1"))

    documents = MagicMock()
    documents.add = AsyncMock()

    decisions = MagicMock()
    decisions.set = AsyncMock()

    memory = MagicMock()
    memory.add_facts = AsyncMock()

    tasks = MagicMock()
    tasks.add = AsyncMock()

    run_history = MagicMock()
    run_history.record = AsyncMock(return_value=SimpleNamespace(id="run-1"))

    bus = MagicMock()
    bus.publish = AsyncMock(return_value=1)

    commit_service = ExecutionCommitService(
        execution_service=execution_service,
        library_service=library,
        documents_service=documents,
        decisions_service=decisions,
        memory_service=memory,
        workspace_tasks_service=tasks,
        run_history_service=run_history,
        event_bus=bus,
    )

    result = await commit_service.commit_outputs("e-1", accept_all=True)

    # 1 library item committed
    assert result["committed"]["library"] == 1
    library.add.assert_awaited_once()

    # run_history always written regardless of outputs
    run_history.record.assert_awaited_once()

    # workspace.refresh event published
    bus.publish.assert_awaited_once_with(
        "workspace.refresh",
        {"workspace_id": "ws-1"},
    )
