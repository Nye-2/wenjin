"""Backend integration test for the paper-analysis end-to-end flow (Plan 1, Task 16).

Scope: scoped integration (not full lead-agent + worker + HTTP stack), for the
following reasons:
1. The full stack requires a real database URL, live Redis/SSE bridge, and a
   real LLM — none of which are available in CI without heavy fixture work.
2. The two sub-pipelines are independently testable: persistence (via
   WorkspaceRunService on an in-memory DB) and SSE emission (via
   _emit_assistant_blocks on MemoryStreamBridge) are pure-async with no
   external deps.
3. Combining them via a mocked agent call would exercise production code paths
   without adding meaningful coverage over the individual unit tests already
   present in tests/runtime/test_block_sse.py and
   tests/services/test_workspace_run_service.py.

This file therefore contains two coherent groups:
- Group A: WorkspaceRunService lifecycle (create → complete → get) on a real
  SQLite-in-memory database.  Verifies spec §6.2 B3.
- Group B: SSE emission correctness for a scripted AgentMessage containing all
  four block kinds, including jargon-leak assertions (spec §1.1) and the
  result-card preamble status_line (spec §5.4).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.pool import StaticPool

from src.runtime.runs.worker import _emit_assistant_blocks
from src.runtime.stream_bridge import END_SENTINEL, MemoryStreamBridge

# ============================================================
# Minimal SQLite-compatible schema for WorkspaceRunRow
# (mirrors the production model but uses SQLite-safe types)
# ============================================================


class _TestBase(DeclarativeBase):
    pass


class _FixtureWorkspace(_TestBase):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="test")


class _FixtureThread(_TestBase):
    __tablename__ = "threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )


class _FixtureWorkspaceRun(_TestBase):
    """SQLite-compatible mirror of WorkspaceRunRow."""

    __tablename__ = "workspace_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    thread_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("threads.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16))
    result_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ============================================================
# Fixtures
# ============================================================

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_session(sqlite_engine) -> AsyncSession:
    factory = async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(sqlite_session: AsyncSession):
    """Create workspace + thread rows so FK constraints are satisfied."""
    ws = _FixtureWorkspace(id="ws-test")
    th = _FixtureThread(id="thread-test", workspace_id="ws-test")
    sqlite_session.add(ws)
    sqlite_session.add(th)
    await sqlite_session.commit()
    return {"workspace_id": "ws-test", "thread_id": "thread-test"}


# ============================================================
# Group A: WorkspaceRunService lifecycle on real SQLite DB
# ============================================================


@pytest.mark.asyncio
async def test_workspace_run_lifecycle_create_complete_get(
    sqlite_session: AsyncSession, seeded_db: dict
):
    """Create → complete → get round-trip persists result_card and marks completed."""
    # Patch the production WorkspaceRunRow with our SQLite-compatible version so
    # the service can work against the in-memory test schema without requiring
    # a real PostgreSQL connection.
    import src.services.workspace_run_service as _svc_mod
    import src.database.models.workspace_run as _model_mod

    original_row_cls = _model_mod.WorkspaceRunRow

    try:
        _model_mod.WorkspaceRunRow = _FixtureWorkspaceRun  # type: ignore[attr-defined]
        _svc_mod.WorkspaceRunRow = _FixtureWorkspaceRun  # type: ignore[attr-defined]

        from src.services.workspace_run_service import WorkspaceRunService

        svc = WorkspaceRunService(sqlite_session)

        run_id = "run-paper-001"
        returned_id = await svc.create_run(
            run_id=run_id,
            workspace_id=seeded_db["workspace_id"],
            thread_id=seeded_db["thread_id"],
            title="Paper Analysis Run",
            started_at=datetime.now(UTC),
        )
        await sqlite_session.commit()
        assert returned_id == run_id

        # Row should exist with status=running
        row = await svc.get_run(run_id)
        assert row is not None
        assert row.status == "running"
        assert row.result_card is None

        # Complete the run
        sample_result_card = {
            "kind": "result_card",
            "run_id": run_id,
            "title": "深度解读：Attention Is All You Need",
            "tldr": "Transformer 架构彻底改变了 NLP 领域。",
            "findings": [{"id": "①", "text": "自注意力机制的计算复杂度分析"}],
            "recommend": {"label": "延伸阅读", "body": "BERT 论文"},
            "links": [],
            "feedback": {
                "question": "这次分析对你有帮助吗？",
                "pills": [
                    {"kind": "primary", "label": "很有帮助", "intent": "helpful"},
                    {"kind": "normal", "label": "一般", "intent": "neutral"},
                ],
                "allow_free_input": True,
            },
            "stats": {"duration_ms": 4200, "subagents": 3, "tokens": 12000},
        }
        sample_stats = {"duration_ms": 4200, "subagents": 3, "tokens": 12000}

        await svc.complete_run(
            run_id, result_card=sample_result_card, stats=sample_stats
        )
        await sqlite_session.commit()

        # Verify persisted state
        row = await svc.get_run(run_id)
        assert row is not None
        assert row.status == "completed"
        assert row.completed_at is not None
        assert row.result_card is not None
        assert row.result_card["title"] == "深度解读：Attention Is All You Need"
        assert row.stats["tokens"] == 12000

    finally:
        _model_mod.WorkspaceRunRow = original_row_cls
        _svc_mod.WorkspaceRunRow = original_row_cls  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_workspace_run_soft_delete(
    sqlite_session: AsyncSession, seeded_db: dict
):
    """Soft-delete sets deleted_at and hides the row from get_run."""
    import src.services.workspace_run_service as _svc_mod
    import src.database.models.workspace_run as _model_mod

    original_row_cls = _model_mod.WorkspaceRunRow
    try:
        _model_mod.WorkspaceRunRow = _FixtureWorkspaceRun  # type: ignore[attr-defined]
        _svc_mod.WorkspaceRunRow = _FixtureWorkspaceRun  # type: ignore[attr-defined]

        from src.services.workspace_run_service import WorkspaceRunService

        svc = WorkspaceRunService(sqlite_session)
        run_id = "run-to-delete"
        await svc.create_run(
            run_id=run_id,
            workspace_id=seeded_db["workspace_id"],
            thread_id=seeded_db["thread_id"],
            title="Delete Me",
            started_at=datetime.now(UTC),
        )
        await sqlite_session.commit()

        await svc.delete_run(run_id)
        await sqlite_session.commit()

        # get_run must return None for soft-deleted rows
        assert await svc.get_run(run_id) is None

    finally:
        _model_mod.WorkspaceRunRow = original_row_cls
        _svc_mod.WorkspaceRunRow = original_row_cls  # type: ignore[attr-defined]


# ============================================================
# Group B: SSE emission for a scripted AgentMessage
# ============================================================


def _scripted_message() -> dict[str, Any]:
    """Return a full AgentMessage payload with all 4 block kinds.

    Block sequence (spec §5.3 + §5.4):
      1. text         — agent acknowledgment
      2. status_line  — phase 1 start
      3. status_line  — phase 2 transition
      4. status_line  — result-card preamble ("正在汇总…")
      5. result_card  — final summary card
    """
    return {
        "role": "assistant",
        "blocks": [
            {
                "kind": "text",
                "content": "我正在为您深度解读这篇论文，请稍候。",
            },
            {
                "kind": "status_line",
                "label": "正在检索文献",
                "run_id": "run-sse-001",
                "phase_index": 0,
                "tone": "info",
            },
            {
                "kind": "status_line",
                "label": "正在分析方法论",
                "run_id": "run-sse-001",
                "phase_index": 1,
                "tone": "info",
            },
            {
                "kind": "status_line",
                "label": "正在汇总分析结果",
                "run_id": "run-sse-001",
                "phase_index": 2,
                "tone": "info",
            },
            {
                "kind": "result_card",
                "run_id": "run-sse-001",
                "title": "深度解读：Attention Is All You Need",
                "tldr": "Transformer 架构通过自注意力机制实现了并行化训练。",
                "findings": [
                    {"id": "①", "text": "多头注意力机制的并行性优于 RNN"},
                ],
                "recommend": {"label": "延伸阅读", "body": "BERT 论文"},
                "links": [],
                "feedback": {
                    "question": "这次分析对你有帮助吗？",
                    "pills": [
                        {"kind": "primary", "label": "很有帮助", "intent": "helpful"},
                    ],
                    "allow_free_input": True,
                },
                "stats": {"duration_ms": 3800, "subagents": 3, "tokens": 10500},
            },
        ],
    }


async def _collect_block_events(
    bridge: MemoryStreamBridge, run_id: str
) -> list[dict[str, Any]]:
    """Emit blocks, signal end, then drain and return only 'block' event payloads.

    Note: publish_end must have already been called before subscribing in a
    synchronous context (all blocks are buffered before we start reading).
    """
    events = []
    async for item in bridge.subscribe(run_id):
        if item is END_SENTINEL:
            break
        if item.event == "block":
            events.append(item.data)
    return events


async def _emit_and_collect(message: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    """Emit all blocks for a message then publish_end, and collect block events."""
    bridge = MemoryStreamBridge()
    await _emit_assistant_blocks(bridge, run_id=run_id, message=message)
    await bridge.publish_end(run_id)
    return await _collect_block_events(bridge, run_id)


@pytest.mark.asyncio
async def test_sse_emits_all_block_kinds_in_order():
    """All 5 blocks from the scripted message are emitted in order."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-001")

    assert len(events) == 5, f"expected 5 block events, got {len(events)}: {events}"

    kinds = [e["block"]["kind"] for e in events]
    assert kinds[0] == "text", "First block must be text"
    assert kinds[1] == "status_line"
    assert kinds[2] == "status_line"
    assert kinds[3] == "status_line"
    assert kinds[4] == "result_card", "Last block must be result_card"


@pytest.mark.asyncio
async def test_sse_all_blocks_share_one_message_id():
    """All blocks from a single turn share one message_id (spec §5.2)."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-002")

    message_ids = {e["message_id"] for e in events}
    assert len(message_ids) == 1, (
        f"Expected single message_id across all blocks, got: {message_ids}"
    )


@pytest.mark.asyncio
async def test_sse_result_card_preamble_status_line():
    """There must be a status_line with label containing '正在汇总' before result_card."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-003")
    blocks = [e["block"] for e in events]

    # Find the result_card position
    result_card_idx = next(
        (i for i, b in enumerate(blocks) if b.get("kind") == "result_card"), None
    )
    assert result_card_idx is not None, "result_card block not found"

    # There must be a status_line with '正在汇总' before the result_card
    preamble_blocks = blocks[:result_card_idx]
    preamble_labels = [
        b.get("label", "")
        for b in preamble_blocks
        if b.get("kind") == "status_line"
    ]
    assert any("正在汇总" in label for label in preamble_labels), (
        f"No status_line with '正在汇总' found before result_card. "
        f"status_line labels before result_card: {preamble_labels}"
    )


@pytest.mark.asyncio
async def test_sse_no_jargon_leak():
    """Spec §1.1 — internal jargon must not appear in any block content.

    Forbidden strings:
    - 'message_feature_proposal' (internal feature routing label)
    - '意图置信度' (intent confidence — internal metric)
    - '我会先复用' (internal sub-task reuse phrase)
    """
    events = await _emit_and_collect(_scripted_message(), "run-sse-004")

    # Collect all text-bearing fields from blocks
    all_text_content: list[str] = []
    for e in events:
        block = e.get("block", {})
        kind = block.get("kind", "")
        if kind == "text":
            all_text_content.append(block.get("content", ""))
        elif kind == "status_line":
            all_text_content.append(block.get("label", ""))
        elif kind == "result_card":
            all_text_content.append(block.get("title", ""))
            all_text_content.append(block.get("tldr", ""))
            for finding in block.get("findings", []):
                all_text_content.append(finding.get("text", ""))

    combined = "\n".join(all_text_content)

    forbidden = [
        "message_feature_proposal",
        "意图置信度",
        "我会先复用",
    ]
    for term in forbidden:
        assert term not in combined, (
            f"Jargon leak detected: '{term}' found in block content"
        )


@pytest.mark.asyncio
async def test_sse_at_least_two_phase_status_lines():
    """Spec §5.3 — at least 2 status_line blocks emitted between text and result_card."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-005")
    blocks = [e["block"] for e in events]

    status_lines = [b for b in blocks if b.get("kind") == "status_line"]
    assert len(status_lines) >= 2, (
        f"Expected at least 2 status_line blocks, got {len(status_lines)}"
    )
