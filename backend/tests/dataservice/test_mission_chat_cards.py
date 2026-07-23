"""Mission chat card emission: block kind, idempotency, emitter, and wiring tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.credit_reservation import CreditReservation
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.database.models.thread import Thread
from src.dataservice.domains.conversation.block_protocol import (
    ConversationBlockKind,
    blocks_from_message,
    canonical_block_kind,
    normalize_block_payload,
)
from src.dataservice.domains.conversation.contracts import (
    ConversationMessageCreateCommand,
)
from src.dataservice.domains.conversation.models import MessageBlock, ThreadMessage
from src.dataservice.domains.conversation.service import DataServiceConversationService
from src.dataservice.domains.mission import chat_cards
from src.dataservice.domains.mission.chat_cards import (
    MissionChatCardContext,
    MissionChatCardEmitter,
)
from src.dataservice.domains.mission.service import MissionStore
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCreatePayload,
    MissionDispatchClaimPayload,
    MissionItemDraftPayload,
    MissionLeaseClaimPayload,
    MissionPausePayload,
    MissionReviewItemDraftPayload,
    MissionReviewItemsCreatePayload,
    MissionRunPatchPayload,
    MissionStatus,
    MissionUserCommandPayload,
)

MISSION_TABLES = [
    MissionRunRecord.__table__,
    CreditReservation.__table__,
    MissionItemRecord.__table__,
    MissionReviewItemRecord.__table__,
    MissionCommitRecord.__table__,
]

CONVERSATION_TABLES = [
    Thread.__table__,
    ThreadMessage.__table__,
    MessageBlock.__table__,
]

_MISSION_POLICY_SNAPSHOT = {
    "execution_budget": {
        "max_model_calls": 1_000,
        "max_tool_operations": 1_000,
        "max_subagent_jobs": 100,
        "stop_after_total_tokens": 10_000_000,
    }
}


def _context(**overrides: Any) -> MissionChatCardContext:
    values = {
        "mission_id": "mission-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "title": "Federated LLM research gap",
    }
    values.update(overrides)
    return MissionChatCardContext(**values)


def test_mission_card_block_kind_is_canonical_and_preserves_payload() -> None:
    block = {
        "kind": "mission_card",
        "card": "stage_passed",
        "mission_id": "mission-1",
        "stage_id": "research",
        "stage_title": "文献调研",
        "evidence_count": 3,
    }

    assert canonical_block_kind(block) == ConversationBlockKind.MISSION_CARD.value
    assert ConversationBlockKind.MISSION_CARD.value == "mission_card"
    normalized = normalize_block_payload(block)
    assert normalized == block
    assert normalized is not block


def test_mission_card_block_survives_blocks_from_message() -> None:
    blocks = blocks_from_message(
        {
            "content": "",
            "blocks": [
                {
                    "kind": "mission_card",
                    "card": "terminal",
                    "mission_id": "mission-1",
                    "status": "completed",
                    "title": "done",
                }
            ],
        }
    )

    assert blocks == [
        {
            "kind": "mission_card",
            "card": "terminal",
            "mission_id": "mission-1",
            "status": "completed",
            "title": "done",
        }
    ]


@pytest_asyncio.fixture
async def conversation_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Thread.metadata.create_all(
                sync_connection,
                tables=CONVERSATION_TABLES,
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Thread(
                id="thread-1",
                user_id="user-1",
                workspace_id="workspace-1",
                model="gpt-5.6-sol",
                message_count=0,
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


def _card_command(card_id: str, *, thread_id: str = "thread-1") -> ConversationMessageCreateCommand:
    return ConversationMessageCreateCommand(
        thread_id=thread_id,
        user_id="user-1",
        workspace_id="workspace-1",
        role="assistant",
        content="",
        sequence_index=0,
        blocks=[
            {
                "kind": "mission_card",
                "card": "terminal",
                "mission_id": "mission-1",
                "status": "completed",
            }
        ],
        metadata={"card_id": card_id, "card": "terminal", "mission_id": "mission-1"},
    )


@pytest.mark.asyncio
async def test_append_card_message_is_idempotent_on_card_id(
    conversation_session: AsyncSession,
) -> None:
    service = DataServiceConversationService(conversation_session, autocommit=True)

    first, first_created = await service.append_card_message(
        _card_command("mission-1:terminal:completed"),
        card_id="mission-1:terminal:completed",
    )
    second, second_created = await service.append_card_message(
        _card_command("mission-1:terminal:completed"),
        card_id="mission-1:terminal:completed",
    )
    third, third_created = await service.append_card_message(
        _card_command("mission-1:terminal:failed"),
        card_id="mission-1:terminal:failed",
    )

    assert first_created is True
    assert second_created is False
    assert str(second.id) == str(first.id)
    assert third_created is True
    records = await service.list_message_records("thread-1")
    assert len(records) == 2
    assert records[0].metadata_json["card_id"] == "mission-1:terminal:completed"
    assert records[0].blocks[0].block_type == "mission_card"
    assert records[0].blocks[0].payload_json["status"] == "completed"


class _RecordingConversationService:
    """Test double capturing append_card_message calls."""

    def __init__(self, session: Any, *, autocommit: bool = True) -> None:
        self.session = session

    calls: list[tuple[ConversationMessageCreateCommand, str]] = []
    fail_with: Exception | None = None

    async def append_card_message(
        self,
        command: ConversationMessageCreateCommand,
        *,
        card_id: str,
    ) -> tuple[Any, bool]:
        type(self).calls.append((command, card_id))
        if type(self).fail_with is not None:
            raise type(self).fail_with
        return SimpleNamespace(id="message-1"), True


@pytest.fixture
def recorded_emission(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    _RecordingConversationService.calls = []
    _RecordingConversationService.fail_with = None
    monkeypatch.setattr(
        chat_cards,
        "DataServiceConversationService",
        _RecordingConversationService,
    )
    publish = AsyncMock()
    monkeypatch.setattr(chat_cards, "publish_workspace_event", publish)
    return publish


@pytest.mark.asyncio
async def test_emitter_stage_passed_card_shape(recorded_emission: AsyncMock) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.stage_passed(
        _context(),
        stage_id="research",
        stage_title="文献调研",
        evidence_count=5,
    )

    assert len(_RecordingConversationService.calls) == 1
    command, card_id = _RecordingConversationService.calls[0]
    assert card_id == "mission-1:stage_passed:research"
    assert command.role == "assistant"
    assert command.content == ""
    assert command.thread_id == "thread-1"
    assert command.metadata["card_id"] == "mission-1:stage_passed:research"
    assert command.blocks == [
        {
            "kind": "mission_card",
            "card": "stage_passed",
            "mission_id": "mission-1",
            "stage_id": "research",
            "stage_title": "文献调研",
            "evidence_count": 5,
        }
    ]
    recorded_emission.assert_awaited_once_with(
        "workspace-1",
        "thread.updated",
        {"thread": {"id": "thread-1", "workspace_id": "workspace-1"}},
    )


@pytest.mark.asyncio
async def test_emitter_review_request_card_shape(recorded_emission: AsyncMock) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.review_request_created(
        _context(),
        review_items=[
            {"review_item_id": "review-1", "title": "研究空白图谱"},
            {"review_item_id": "review-2", "title": "实验设计稿"},
        ],
    )

    command, card_id = _RecordingConversationService.calls[0]
    assert card_id == "mission-1:review_request:review-1"
    assert command.blocks == [
        {
            "kind": "mission_card",
            "card": "review_request",
            "mission_id": "mission-1",
            "review_item_ids": ["review-1", "review-2"],
            "count": 2,
            "items": [
                {"review_item_id": "review-1", "title": "研究空白图谱"},
                {"review_item_id": "review-2", "title": "实验设计稿"},
            ],
        }
    ]


@pytest.mark.asyncio
async def test_emitter_review_request_skips_empty_batch(
    recorded_emission: AsyncMock,
) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.review_request_created(_context(), review_items=[])

    assert _RecordingConversationService.calls == []
    recorded_emission.assert_not_awaited()


@pytest.mark.asyncio
async def test_emitter_material_request_card_shape(recorded_emission: AsyncMock) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.material_request_created(
        _context(),
        request_id="pause:material:abc",
        title="需要你补充研究材料",
        summary="当前研究缺少继续推进所需的材料。",
    )

    command, card_id = _RecordingConversationService.calls[0]
    assert card_id == "mission-1:material_request:pause:material:abc"
    assert command.blocks == [
        {
            "kind": "mission_card",
            "card": "material_request",
            "mission_id": "mission-1",
            "request_id": "pause:material:abc",
            "title": "需要你补充研究材料",
            "summary": "当前研究缺少继续推进所需的材料。",
        }
    ]


@pytest.mark.asyncio
async def test_emitter_terminal_card_shape(recorded_emission: AsyncMock) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.terminal(_context(), status="failed")

    command, card_id = _RecordingConversationService.calls[0]
    assert card_id == "mission-1:terminal:failed"
    assert command.blocks == [
        {
            "kind": "mission_card",
            "card": "terminal",
            "mission_id": "mission-1",
            "status": "failed",
            "title": "Federated LLM research gap",
        }
    ]


@pytest.mark.asyncio
async def test_emitter_terminal_ignores_nonterminal_status(
    recorded_emission: AsyncMock,
) -> None:
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.terminal(_context(), status="waiting")

    assert _RecordingConversationService.calls == []
    recorded_emission.assert_not_awaited()


@pytest.mark.asyncio
async def test_emitter_contains_failures(recorded_emission: AsyncMock) -> None:
    _RecordingConversationService.fail_with = RuntimeError("db down")
    emitter = MissionChatCardEmitter(session_factory=None)

    await emitter.terminal(_context(), status="completed")

    recorded_emission.assert_not_awaited()


@pytest_asyncio.fixture
async def mission_card_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/mission-cards.db")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Thread.metadata.create_all(
                sync_connection,
                tables=[*MISSION_TABLES, *CONVERSATION_TABLES],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    publish = AsyncMock()
    monkeypatch.setattr(chat_cards, "publish_workspace_event", publish)
    session = factory()
    session.add(
        Thread(
            id="thread-1",
            user_id="user-1",
            workspace_id="workspace-1",
            model="gpt-5.6-sol",
            message_count=0,
        )
    )
    await session.commit()
    store = MissionStore(
        session,
        autocommit=True,
        chat_card_emitter=MissionChatCardEmitter(session_factory=factory),
    )
    yield SimpleNamespace(store=store, session=session, publish=publish)
    await session.close()
    await engine.dispose()


def _create_payload(**overrides: Any) -> MissionCreatePayload:
    values: dict[str, Any] = {
        "workspace_id": "workspace-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "workspace_type": "sci",
        "mission_policy_id": "sci.research",
        "title": "Federated LLM research gap",
        "objective": "Identify a defensible research gap with evidence.",
        "model_id": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "snapshot_json": {"plan_summary": "Scope the literature."},
        "runtime_context_json": {
            "policy_ref": "policy-v1",
            "mission_policy_snapshot": _MISSION_POLICY_SNAPSHOT,
        },
        "mission_idempotency_key": "mission-create-1",
    }
    values.update(overrides)
    return MissionCreatePayload(**values)


async def _claim(store: MissionStore, mission_id: str, *, version: int):
    dispatch_owner = "dispatcher:worker-1"
    dispatched = await store.claim_dispatch_for_run(
        mission_id,
        MissionDispatchClaimPayload(
            worker_id=dispatch_owner,
            expected_state_version=version,
            ttl_seconds=60,
        ),
    )
    return await store.claim_run_lease(
        mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            dispatch_owner=dispatch_owner,
            dispatch_epoch=dispatched.dispatch_epoch,
            expected_state_version=dispatched.state_version,
            ttl_seconds=120,
        ),
    )


async def _card_messages(env: Any) -> list[tuple[ThreadMessage, list[MessageBlock]]]:
    messages = list(
        (
            await env.session.execute(
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == "thread-1")
                .order_by(ThreadMessage.sequence_index.asc())
            )
        )
        .scalars()
        .all()
    )
    result: list[tuple[ThreadMessage, list[MessageBlock]]] = []
    for message in messages:
        blocks = list(
            (
                await env.session.execute(
                    select(MessageBlock).where(MessageBlock.message_id == message.id)
                )
            )
            .scalars()
            .all()
        )
        result.append((message, blocks))
    return result


@pytest.mark.asyncio
async def test_stage_pass_emission_after_append(mission_card_env: Any) -> None:
    env = mission_card_env
    created = await env.store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    claimed = await _claim(env.store, mission_id, version=created.mission.state_version)

    await env.store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="evidence",
                    operation_id="op-evidence-1",
                    phase="completed",
                    producer="workspace_agent",
                    summary="Checked one source",
                    payload_json={"reference_id": "source-1"},
                )
            ],
            snapshot_json={
                "plan_summary": "Scope the literature.",
                "stage_acceptance": {
                    "research": {"result": "pass", "title": "文献调研"},
                },
            },
        ),
    )
    await env.store.wait_chat_card_emissions()

    cards = await _card_messages(env)
    assert len(cards) == 1
    message, blocks = cards[0]
    assert message.role == "assistant"
    assert message.metadata_json["card_id"] == f"{mission_id}:stage_passed:research"
    assert message.metadata_json["card"] == "stage_passed"
    assert len(blocks) == 1
    assert blocks[0].block_type == "mission_card"
    assert blocks[0].payload_json == {
        "kind": "mission_card",
        "card": "stage_passed",
        "mission_id": mission_id,
        "stage_id": "research",
        "stage_title": "文献调研",
        "evidence_count": 1,
    }
    env.publish.assert_awaited_once_with(
        "workspace-1",
        "thread.updated",
        {"thread": {"id": "thread-1", "workspace_id": "workspace-1"}},
    )


@pytest.mark.asyncio
async def test_stage_pass_reappend_without_new_pass_emits_nothing(
    mission_card_env: Any,
) -> None:
    env = mission_card_env
    created = await env.store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    claimed = await _claim(env.store, mission_id, version=created.mission.state_version)
    snapshot = {
        "plan_summary": "Scope the literature.",
        "stage_acceptance": {"research": {"result": "pass", "title": "文献调研"}},
    }
    await env.store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="evidence",
                    operation_id="op-evidence-1",
                    phase="completed",
                    producer="workspace_agent",
                    summary="Checked one source",
                    payload_json={"reference_id": "source-1"},
                )
            ],
            snapshot_json=snapshot,
        ),
    )
    await env.store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version + 1,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="evidence",
                    operation_id="op-evidence-2",
                    phase="completed",
                    producer="workspace_agent",
                    summary="Checked another source",
                    payload_json={"reference_id": "source-2"},
                )
            ],
            snapshot_json=snapshot,
        ),
    )
    await env.store.wait_chat_card_emissions()

    cards = await _card_messages(env)
    assert len(cards) == 1
    assert cards[0][0].metadata_json["card_id"] == f"{mission_id}:stage_passed:research"


@pytest.mark.asyncio
async def test_review_items_creation_emits_review_request_card(
    mission_card_env: Any,
) -> None:
    env = mission_card_env
    created = await env.store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    claimed = await _claim(env.store, mission_id, version=created.mission.state_version)

    await env.store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-gap-map",
                    output_key="literature_gap_map",
                    target_kind="document",
                    target_room="documents",
                    title="研究空白图谱",
                    risk_level="medium",
                    preview_json={"summary": "gap map"},
                ),
                MissionReviewItemDraftPayload(
                    review_item_id="review-experiment-plan",
                    output_key="experiment_plan",
                    target_kind="document",
                    target_room="documents",
                    title="实验设计稿",
                    risk_level="medium",
                    preview_json={"summary": "experiment plan"},
                ),
            ],
        ),
    )
    await env.store.wait_chat_card_emissions()

    cards = await _card_messages(env)
    assert len(cards) == 1
    message, blocks = cards[0]
    assert message.metadata_json["card_id"] == f"{mission_id}:review_request:review-gap-map"
    assert blocks[0].payload_json == {
        "kind": "mission_card",
        "card": "review_request",
        "mission_id": mission_id,
        "review_item_ids": ["review-gap-map", "review-experiment-plan"],
        "count": 2,
        "items": [
            {"review_item_id": "review-gap-map", "title": "研究空白图谱"},
            {"review_item_id": "review-experiment-plan", "title": "实验设计稿"},
        ],
    }


@pytest.mark.asyncio
async def test_pause_emits_material_request_card(mission_card_env: Any) -> None:
    env = mission_card_env
    created = await env.store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    admitted = await env.store.apply_initial_admission(
        mission_id,
        status=MissionStatus.PLANNING,
        snapshot_json={"plan_summary": "Scope the literature."},
        item=MissionItemDraftPayload(
            item_type="mission_admitted",
            phase="completed",
            producer="mission_admission",
            summary="Mission admitted under the active free pricing policy",
            payload_json={},
        ),
    )
    assert admitted.status == "planning"

    await env.store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="pause:material:req-1",
            reason="external_data",
            producer="mission_runtime",
            pending_request={"stage_id": "research"},
        ),
    )
    await env.store.wait_chat_card_emissions()

    cards = await _card_messages(env)
    assert len(cards) == 1
    message, blocks = cards[0]
    assert (
        message.metadata_json["card_id"]
        == f"{mission_id}:material_request:pause:material:req-1"
    )
    assert blocks[0].payload_json == {
        "kind": "mission_card",
        "card": "material_request",
        "mission_id": mission_id,
        "request_id": "pause:material:req-1",
        "title": "需要你补充研究材料",
        "summary": "当前研究缺少继续推进所需的材料，请在对话中补充或上传文件。",
    }


@pytest.mark.asyncio
async def test_terminal_transition_emits_terminal_card(mission_card_env: Any) -> None:
    env = mission_card_env
    created = await env.store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    queued = await env.store.append_command_once(
        mission_id,
        MissionUserCommandPayload(
            command_id="cancel-1",
            command_type="cancel",
            summary="User cancelled",
            payload_json={"reason": "user_cancelled"},
        ),
    )
    claimed = await _claim(env.store, mission_id, version=queued.mission.state_version)
    await env.store.apply_commands_and_advance_cursor(
        mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=queued.mission.last_command_seq,
            patch=MissionRunPatchPayload(status="cancelled"),
        ),
    )
    await env.store.wait_chat_card_emissions()

    cards = await _card_messages(env)
    assert len(cards) == 1
    message, blocks = cards[0]
    assert message.metadata_json["card_id"] == f"{mission_id}:terminal:cancelled"
    assert blocks[0].payload_json == {
        "kind": "mission_card",
        "card": "terminal",
        "mission_id": mission_id,
        "status": "cancelled",
        "title": "Federated LLM research gap",
    }


@pytest.mark.asyncio
async def test_emission_failure_does_not_break_mission_mutation(
    mission_card_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = mission_card_env

    class _BrokenSessionFactory:
        def __call__(self) -> Any:
            raise RuntimeError("no session factory available")

    broken_store = MissionStore(
        env.session,
        autocommit=True,
        chat_card_emitter=MissionChatCardEmitter(
            session_factory=_BrokenSessionFactory()
        ),
    )
    created = await broken_store.create_run(_create_payload())
    mission_id = created.mission.mission_id
    admitted = await broken_store.apply_initial_admission(
        mission_id,
        status=MissionStatus.PLANNING,
        snapshot_json={"plan_summary": "Scope the literature."},
        item=MissionItemDraftPayload(
            item_type="mission_admitted",
            phase="completed",
            producer="mission_admission",
            summary="Mission admitted under the active free pricing policy",
            payload_json={},
        ),
    )
    assert admitted.status == "planning"

    await broken_store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="pause:material:req-2",
            reason="external_data",
            producer="mission_runtime",
            pending_request={},
        ),
    )
    await broken_store.wait_chat_card_emissions()

    run = await broken_store.load_run_snapshot(mission_id)
    assert run is not None
    assert run.status == "waiting"
    assert await _card_messages(env) == []
