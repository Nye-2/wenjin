"""Release verification through migration 110 and PostgreSQL accounting locks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import BigInteger, func, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.contracts.billing import CreditTransactionType, ThreadTurnBillingStatus
from src.contracts.model_usage import ModelUsage
from src.database.models.credit import CreditTransaction
from src.database.models.model_catalog import ModelCatalogEntry, ModelCategory
from src.database.models.pricing_policy import PricingPolicy, PricingPolicyKind
from src.database.models.thread import Thread
from src.database.models.thread_turn_billing import ThreadTurnBilling
from src.database.models.user import User
from src.database.models.workspace import Workspace, WorkspaceType
from src.dataservice.common.errors import CreditOverdraftLimitError
from src.dataservice.domains.conversation.models import ThreadMessage
from src.dataservice.domains.thread_turn_billing.service import (
    ThreadTurnBillingService,
)
from src.dataservice.domains.workspace.models import WorkspaceMembership
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
)
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnAuthorizePayload,
    ThreadTurnCompletePayload,
    ThreadTurnReleasePayload,
)
from src.models.capability_profile import GenerationAPI

pytestmark = pytest.mark.integration


MODEL_POLICY_CONFIG = {
    "input_weight": 0.3,
    "cached_input_weight": 0.05,
    "output_weight": 1.0,
    "reasoning_weight": 1.0,
    "credits_per_1k_weighted_tokens": 6.0,
    "min_chat_credits": 0,
    "min_mission_model_credits": 10,
    "cost_guard_multiplier": 20.0,
    "raw_cost": {},
    "free_tokens": 0,
    "max_overdraft_credits": 0,
    "chat_turn_token_reserve": 1_000,
    "chat_turn_max_credits": 10,
    "chat_turn_authorization_ttl_seconds": 300,
}


@dataclass(slots=True)
class BillingScenario:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    user_id: str
    workspace_id: str
    thread_id: str
    model_id: str


Operation = Callable[[ThreadTurnBillingService], Awaitable[Any]]


def _uuid() -> str:
    return str(uuid4())


@pytest.fixture
async def billing_scenario(
    postgres_110_database: Any,
) -> AsyncIterator[BillingScenario]:
    engine = create_async_engine(
        postgres_110_database.async_url,
        pool_size=4,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
    suffix = uuid4().hex[:12]
    user_id = _uuid()
    workspace_id = _uuid()
    thread_id = _uuid()
    pricing_policy_id = _uuid()
    model_id = f"gpt-5.6-terra-{suffix}"
    now = datetime.now(UTC)

    async with session_factory.begin() as session:
        session.add_all(
            [
                PricingPolicy(
                    id=pricing_policy_id,
                    policy_key=f"release-model-{suffix}",
                    policy_kind=PricingPolicyKind.MODEL_USAGE,
                    name="Runtime accounting release verification",
                    enabled=True,
                    version=1,
                    config_json=MODEL_POLICY_CONFIG,
                ),
                ModelCatalogEntry(
                    id=_uuid(),
                    model_id=model_id,
                    display_name="Release verification Terra",
                    generation_api=GenerationAPI.CHAT_COMPLETIONS,
                    provider_name="Release verification",
                    category=ModelCategory.LLM,
                    model_name=model_id,
                    base_url="https://release-verification.invalid/v1",
                    encrypted_api_key="release-verification-no-provider-key",
                    enabled=True,
                    is_default=False,
                    capability_profile_json={},
                    capability_probe_json={},
                    capability_probe_hash="0" * 64,
                    capability_observed_at=now,
                    pricing_policy_id=pricing_policy_id,
                ),
                User(
                    id=user_id,
                    email=f"runtime-accounting-{suffix}@example.invalid",
                    name="Runtime accounting verification",
                    hashed_password="not-a-login-credential",
                    is_active=True,
                    is_superuser=False,
                    credits=10,
                    reserved_credits=0,
                    thread_consumed_tokens=0,
                    reserved_thread_free_tokens=0,
                    total_credits_earned=10,
                    total_credits_spent=0,
                ),
            ]
        )
        await session.flush()
        session.add(
            Workspace(
                id=workspace_id,
                user_id=user_id,
                name="Runtime accounting workspace",
                type=WorkspaceType.SCI,
                config={},
            )
        )
        await session.flush()
        session.add(
            WorkspaceMembership(
                id=_uuid(),
                workspace_id=workspace_id,
                user_id=user_id,
                role="owner",
                status="active",
            )
        )
        session.add(
            Thread(
                id=thread_id,
                user_id=user_id,
                workspace_id=workspace_id,
                title="Runtime accounting thread",
                model=model_id,
                message_count=0,
            )
        )

    scenario = BillingScenario(
        engine=engine,
        session_factory=session_factory,
        user_id=user_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        model_id=model_id,
    )
    try:
        yield scenario
    finally:
        await engine.dispose()


def _authorize_payload(
    scenario: BillingScenario,
    *,
    key: str,
    content: str = "Verify PostgreSQL runtime accounting",
) -> ThreadTurnAuthorizePayload:
    return ThreadTurnAuthorizePayload(
        idempotency_key=key,
        model_id=scenario.model_id,
        user_message=ConversationMessageCreatePayload(
            thread_id=scenario.thread_id,
            user_id=scenario.user_id,
            workspace_id=scenario.workspace_id,
            role="user",
            content=content,
            sequence_index=0,
            timestamp=datetime.now(UTC),
            metadata={"surface": "release_verification"},
        ),
    )


def _completion_payload(scenario: BillingScenario) -> ThreadTurnCompletePayload:
    return ThreadTurnCompletePayload(
        user_id=scenario.user_id,
        assistant_message=ConversationMessageCreatePayload(
            thread_id=scenario.thread_id,
            user_id=scenario.user_id,
            workspace_id=scenario.workspace_id,
            role="assistant",
            content="PostgreSQL serialized the accounting transition.",
            sequence_index=1,
            timestamp=datetime.now(UTC),
            metadata={"surface": "release_verification"},
        ),
        token_usage=ModelUsage(
            input_tokens=1_000,
            cached_input_tokens=100,
            output_tokens=500,
            reasoning_tokens=200,
            total_tokens=1_500,
        ),
    )


async def _set_transaction_timeouts(session: AsyncSession) -> None:
    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    await session.execute(text("SET LOCAL statement_timeout = '10s'"))


async def _wait_until_backend_is_lock_blocked(
    lock_owner: AsyncSession,
    *,
    blocked_pid: int,
) -> None:
    for _ in range(200):
        wait_event_type = (
            await lock_owner.execute(
                text(
                    "SELECT wait_event_type FROM pg_stat_activity "
                    "WHERE pid = :blocked_pid"
                ),
                {"blocked_pid": blocked_pid},
            )
        ).scalar_one_or_none()
        if wait_event_type == "Lock":
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"PostgreSQL backend {blocked_pid} never entered a row-lock wait"
    )


async def _run_with_observed_user_lock_race(
    scenario: BillingScenario,
    *,
    first: Operation,
    second: Operation,
) -> tuple[Any, Any]:
    """Run two production service calls after proving the second waits on users."""

    first_has_lock = asyncio.Event()
    second_pid: asyncio.Queue[int] = asyncio.Queue(maxsize=1)

    async def run_first() -> Any:
        async with scenario.session_factory() as session:
            await _set_transaction_timeouts(session)
            first_pid = (
                await session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            locked_user_id = (
                await session.execute(
                    text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"),
                    {"user_id": scenario.user_id},
                )
            ).scalar_one()
            assert locked_user_id == scenario.user_id
            first_has_lock.set()
            blocked_pid = await asyncio.wait_for(second_pid.get(), timeout=2)
            assert blocked_pid != first_pid
            await _wait_until_backend_is_lock_blocked(
                session,
                blocked_pid=blocked_pid,
            )
            try:
                result = await first(ThreadTurnBillingService(session, autocommit=False))
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def run_second() -> Any:
        await first_has_lock.wait()
        async with scenario.session_factory() as session:
            await _set_transaction_timeouts(session)
            pid = (
                await session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            await second_pid.put(pid)
            try:
                result = await second(ThreadTurnBillingService(session, autocommit=False))
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    return await asyncio.wait_for(
        asyncio.gather(run_first(), run_second()),
        timeout=15,
    )


async def _authorize_and_commit(
    scenario: BillingScenario,
    *,
    key: str,
) -> Any:
    async with scenario.session_factory() as session:
        await _set_transaction_timeouts(session)
        result = await ThreadTurnBillingService(
            session,
            autocommit=False,
        ).authorize(_authorize_payload(scenario, key=key))
        await session.commit()
        return result


def _normalized_sql(value: Any) -> str:
    normalized = "".join(str(value or "").lower().replace('"', "").split())
    return normalized.replace("::charactervarying", "").replace("::text", "")


def _index_predicate(index: dict[str, Any]) -> str:
    return _normalized_sql(
        dict(index.get("dialect_options") or {}).get("postgresql_where")
    )


def _assert_110_schema(sync_connection: Any) -> None:
    inspector = inspect(sync_connection)
    revision = sync_connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    assert revision == "110_deduplicate_mission_references"

    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    for name in ("thread_consumed_tokens", "reserved_thread_free_tokens"):
        assert isinstance(user_columns[name]["type"], BigInteger)
        assert user_columns[name]["nullable"] is False
        assert "0" in str(user_columns[name]["default"])

    credit_columns = {
        column["name"]: column
        for column in inspector.get_columns("credit_transactions")
    }
    assert credit_columns["idempotency_key"]["nullable"] is True
    assert credit_columns["idempotency_key"]["type"].length == 200

    billing_columns = {
        column["name"]: column
        for column in inspector.get_columns("thread_turn_billings")
    }
    assert {
        "id",
        "user_id",
        "workspace_id",
        "thread_id",
        "user_message_id",
        "assistant_message_id",
        "idempotency_key",
        "request_hash",
        "model_id",
        "status",
        "reserved_credits",
        "reserved_free_tokens",
        "settled_credits",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "pricing_snapshot_json",
        "transaction_id",
        "expires_at",
        "settled_at",
        "released_at",
        "release_reason",
        "created_at",
        "updated_at",
    } == set(billing_columns)
    assert isinstance(billing_columns["pricing_snapshot_json"]["type"], JSONB)
    assert billing_columns["idempotency_key"]["nullable"] is False
    assert billing_columns["request_hash"]["type"].length == 64
    assert billing_columns["expires_at"]["nullable"] is False

    mission_columns = {
        column["name"]: column
        for column in inspector.get_columns("mission_runs")
    }
    assert mission_columns["mission_policy_id"]["nullable"] is False

    unique_columns = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("thread_turn_billings")
    }
    assert {
        ("idempotency_key",),
        ("user_message_id",),
        ("assistant_message_id",),
        ("transaction_id",),
    } <= unique_columns

    credit_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("credit_transactions")
    }
    credit_idempotency = credit_indexes[
        "uq_credit_transactions_user_type_idempotency"
    ]
    assert credit_idempotency["unique"] is True
    assert credit_idempotency["column_names"] == [
        "user_id",
        "transaction_type",
        "idempotency_key",
    ]
    assert "idempotency_keyisnotnull" in _index_predicate(credit_idempotency)

    billing_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("thread_turn_billings")
    }
    assert {
        "ix_thread_turn_billings_user_id",
        "ix_thread_turn_billings_thread_id",
        "ix_thread_turn_billings_workspace_id",
        "ix_thread_turn_billings_authorized_expiry",
    } <= set(billing_indexes)
    authorized_expiry = billing_indexes[
        "ix_thread_turn_billings_authorized_expiry"
    ]
    assert authorized_expiry["unique"] is False
    assert authorized_expiry["column_names"] == ["expires_at", "id"]
    predicate = _index_predicate(authorized_expiry)
    assert "status" in predicate
    assert "authorized" in predicate

    user_checks = {
        constraint["name"]: _normalized_sql(constraint["sqltext"])
        for constraint in inspector.get_check_constraints("users")
    }
    assert "thread_consumed_tokens>=0" in user_checks[
        "ck_users_thread_token_counters_nonnegative"
    ]
    assert "reserved_thread_free_tokens>=0" in user_checks[
        "ck_users_thread_token_counters_nonnegative"
    ]
    assert "reserved_credits>=0" in user_checks[
        "ck_users_credit_counters_nonnegative"
    ]
    assert "total_credits_spent>=0" in user_checks[
        "ck_users_credit_counters_nonnegative"
    ]

    billing_checks = {
        constraint["name"]: _normalized_sql(constraint["sqltext"])
        for constraint in inspector.get_check_constraints("thread_turn_billings")
    }
    assert {
        "ck_thread_turn_billings_status",
        "ck_thread_turn_billings_nonnegative_money",
        "ck_thread_turn_billings_nonnegative_usage",
        "ck_thread_turn_billings_state_timestamps",
        "ck_thread_turn_billings_usage_state",
        "ck_thread_turn_billings_transaction_state",
    } <= set(billing_checks)
    assert "settled_credits<=reserved_credits" in billing_checks[
        "ck_thread_turn_billings_nonnegative_money"
    ]
    assert "cached_input_tokens<=input_tokens" in billing_checks[
        "ck_thread_turn_billings_nonnegative_usage"
    ]
    assert "status='settled'" in billing_checks[
        "ck_thread_turn_billings_state_timestamps"
    ]
    assert "total_tokens>0" in billing_checks[
        "ck_thread_turn_billings_usage_state"
    ]
    assert "transaction_idisnotnull" in billing_checks[
        "ck_thread_turn_billings_transaction_state"
    ]

    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("thread_turn_billings")
    }
    expected_foreign_keys = {
        ("user_id",): ("users", ["id"], "CASCADE"),
        ("workspace_id",): ("workspaces", ["id"], "SET NULL"),
        ("user_message_id",): ("thread_messages", ["id"], "SET NULL"),
        ("assistant_message_id",): ("thread_messages", ["id"], "SET NULL"),
        ("transaction_id",): ("credit_transactions", ["id"], "RESTRICT"),
    }
    for constrained_columns, (
        referred_table,
        referred_columns,
        ondelete,
    ) in expected_foreign_keys.items():
        foreign_key = foreign_keys[constrained_columns]
        assert foreign_key["referred_table"] == referred_table
        assert foreign_key["referred_columns"] == referred_columns
        assert str(foreign_key["options"].get("ondelete") or "").upper() == ondelete
    assert ("thread_id",) not in foreign_keys


@pytest.mark.asyncio
async def test_empty_postgres_upgrades_to_110_with_runtime_accounting_schema(
    postgres_110_database: Any,
) -> None:
    engine = create_async_engine(postgres_110_database.async_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_assert_110_schema)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_data_bearing_postgres_upgrades_from_108_to_110_ssot(
    postgres_108_database: Any,
) -> None:
    mission_id = _uuid()
    snapshot = {
        "subagent_summary": {"latest": [{"job_id": "worker-1"}]},
        "team_summary": "旧的快照投影",
        "quality_summary": {"highlights": ["应保留"]},
    }
    evidence_payloads = [
        {"reference_id": "doi:10.1000/example", "title": "初次观察"},
        {"reference_id": "doi:10.1000/example", "title": "重复观察"},
        {"reference_id": "", "title": "无语义标识的材料"},
        {"title": "历史材料"},
    ]
    engine = create_async_engine(postgres_108_database.async_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO mission_runs (
                        mission_id, workspace_id, user_id, workspace_type,
                        mission_policy_id, title, objective, status, review_mode,
                        model_id, reasoning_effort, snapshot_json,
                        runtime_context_json, evidence_count, last_item_seq
                    ) VALUES (
                        :mission_id, :workspace_id, :user_id, 'sci',
                        'release-verification-policy', '带数据迁移验证',
                        '验证投影单一事实来源切换', 'completed',
                        'balanced_default', 'gpt-5.6-terra', 'xhigh',
                        CAST(:snapshot_json AS JSONB), '{}'::jsonb, 99, 5
                    )
                    """
                ),
                {
                    "mission_id": mission_id,
                    "workspace_id": _uuid(),
                    "user_id": _uuid(),
                    "snapshot_json": json.dumps(snapshot, ensure_ascii=False),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO mission_items (
                        id, mission_id, seq, item_type, phase, payload_json
                    ) VALUES (
                        :id, :mission_id, :seq, :item_type, 'completed',
                        CAST(:payload_json AS JSONB)
                    )
                    """
                ),
                [
                    {
                        "id": _uuid(),
                        "mission_id": mission_id,
                        "seq": index,
                        "item_type": "evidence",
                        "payload_json": json.dumps(payload, ensure_ascii=False),
                    }
                    for index, payload in enumerate(evidence_payloads, start=1)
                ]
                + [
                    {
                        "id": _uuid(),
                        "mission_id": mission_id,
                        "seq": 5,
                        "item_type": "artifact",
                        "payload_json": json.dumps(
                            {"reference_id": "doi:10.1000/example"}
                        ),
                    }
                ],
            )
    finally:
        await engine.dispose()

    postgres_108_database.upgrade_to("110_deduplicate_mission_references")

    upgraded_engine = create_async_engine(postgres_108_database.async_url)
    try:
        async with upgraded_engine.connect() as connection:
            revision = (
                await connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )
            ).scalar_one()
            row = (
                await connection.execute(
                    text(
                        "SELECT snapshot_json, evidence_count "
                        "FROM mission_runs WHERE mission_id = :mission_id"
                    ),
                    {"mission_id": mission_id},
                )
            ).one()
            item_count = (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM mission_items "
                        "WHERE mission_id = :mission_id"
                    ),
                    {"mission_id": mission_id},
                )
            ).scalar_one()
    finally:
        await upgraded_engine.dispose()

    assert revision == "110_deduplicate_mission_references"
    assert row.snapshot_json == {
        "quality_summary": {"highlights": ["应保留"]}
    }
    assert row.evidence_count == 3
    assert item_count == 5


@pytest.mark.asyncio
async def test_concurrent_authorize_cannot_spend_same_user_capacity_twice(
    billing_scenario: BillingScenario,
) -> None:
    first_payload = _authorize_payload(
        billing_scenario,
        key=f"capacity-first:{uuid4().hex}",
    )
    second_payload = _authorize_payload(
        billing_scenario,
        key=f"capacity-second:{uuid4().hex}",
    )

    first, second = await _run_with_observed_user_lock_race(
        billing_scenario,
        first=lambda service: service.authorize(first_payload),
        second=lambda service: service.authorize(second_payload),
    )

    assert not isinstance(first, Exception)
    assert first.created is True
    assert first.billing.reserved_credits == 6
    assert isinstance(second, CreditOverdraftLimitError)
    async with billing_scenario.session_factory() as session:
        user = await session.get(User, billing_scenario.user_id)
        assert user is not None
        assert user.credits == 10
        assert user.reserved_credits == 6
        assert user.reserved_thread_free_tokens == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ThreadTurnBilling)
                .where(ThreadTurnBilling.user_id == billing_scenario.user_id)
            )
        ) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ThreadMessage)
                .where(ThreadMessage.thread_id == billing_scenario.thread_id)
            )
        ) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.user_id == billing_scenario.user_id)
            )
        ) == 0


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_creates_one_billing_and_user_message(
    billing_scenario: BillingScenario,
) -> None:
    payload = _authorize_payload(
        billing_scenario,
        key=f"same-idempotency:{uuid4().hex}",
    )

    first, second = await _run_with_observed_user_lock_race(
        billing_scenario,
        first=lambda service: service.authorize(payload),
        second=lambda service: service.authorize(payload),
    )

    assert not isinstance(first, Exception)
    assert not isinstance(second, Exception)
    assert first.created is True
    assert second.created is False
    assert second.billing.id == first.billing.id
    assert second.user_message is not None
    assert first.user_message is not None
    assert second.user_message.id == first.user_message.id
    async with billing_scenario.session_factory() as session:
        user = await session.get(User, billing_scenario.user_id)
        assert user is not None
        assert user.credits == 10
        assert user.reserved_credits == 6
        billings = list(
            (
                await session.scalars(
                    select(ThreadTurnBilling).where(
                        ThreadTurnBilling.user_id == billing_scenario.user_id
                    )
                )
            ).all()
        )
        messages = list(
            (
                await session.scalars(
                    select(ThreadMessage).where(
                        ThreadMessage.thread_id == billing_scenario.thread_id
                    )
                )
            ).all()
        )
        assert len(billings) == 1
        assert len(messages) == 1
        assert billings[0].user_message_id == messages[0].id


@pytest.mark.asyncio
async def test_settle_then_concurrent_thread_delete_has_no_deadlock_and_one_ledger(
    billing_scenario: BillingScenario,
) -> None:
    authorized = await _authorize_and_commit(
        billing_scenario,
        key=f"settle-delete:{uuid4().hex}",
    )

    settled, deleted = await _run_with_observed_user_lock_race(
        billing_scenario,
        first=lambda service: service.complete(
            authorized.billing.id,
            _completion_payload(billing_scenario),
        ),
        second=lambda service: service.delete_thread(
            thread_id=billing_scenario.thread_id,
            user_id=billing_scenario.user_id,
        ),
    )

    if isinstance(settled, Exception):
        raise settled
    assert settled.billing.status is ThreadTurnBillingStatus.SETTLED
    assert deleted is True
    async with billing_scenario.session_factory() as session:
        user = await session.get(User, billing_scenario.user_id)
        billing = await session.get(ThreadTurnBilling, authorized.billing.id)
        transactions = list(
            (
                await session.scalars(
                    select(CreditTransaction).where(
                        CreditTransaction.user_id == billing_scenario.user_id
                    )
                )
            ).all()
        )
        assert user is not None
        assert billing is not None
        assert user.credits == 5
        assert user.reserved_credits == 0
        assert user.reserved_thread_free_tokens == 0
        assert user.thread_consumed_tokens == 1_500
        assert user.total_credits_spent == 5
        assert billing.status == ThreadTurnBillingStatus.SETTLED.value
        assert billing.reserved_credits == 6
        assert billing.settled_credits == 5
        assert billing.total_tokens == 1_500
        assert billing.thread_id == billing_scenario.thread_id
        assert billing.user_message_id is None
        assert billing.assistant_message_id is None
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction.id == billing.transaction_id
        assert transaction.transaction_type is CreditTransactionType.THREAD_TOKEN_CONSUME
        assert transaction.amount == -5
        assert transaction.balance_after == 5
        assert transaction.idempotency_key == f"thread-turn:{billing.id}"
        assert await session.get(Thread, billing_scenario.thread_id) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ThreadMessage)
                .where(ThreadMessage.thread_id == billing_scenario.thread_id)
            )
        ) == 0


@pytest.mark.asyncio
async def test_thread_delete_then_concurrent_release_has_no_deadlock_or_ledger(
    billing_scenario: BillingScenario,
) -> None:
    authorized = await _authorize_and_commit(
        billing_scenario,
        key=f"delete-release:{uuid4().hex}",
    )

    deleted, released = await _run_with_observed_user_lock_race(
        billing_scenario,
        first=lambda service: service.delete_thread(
            thread_id=billing_scenario.thread_id,
            user_id=billing_scenario.user_id,
        ),
        second=lambda service: service.release(
            authorized.billing.id,
            ThreadTurnReleasePayload(
                user_id=billing_scenario.user_id,
                reason="concurrent release verification",
            ),
        ),
    )

    assert deleted is True
    assert not isinstance(released, Exception)
    assert released.status is ThreadTurnBillingStatus.RELEASED
    async with billing_scenario.session_factory() as session:
        user = await session.get(User, billing_scenario.user_id)
        billing = await session.get(ThreadTurnBilling, authorized.billing.id)
        assert user is not None
        assert billing is not None
        assert user.credits == 10
        assert user.reserved_credits == 0
        assert user.reserved_thread_free_tokens == 0
        assert user.thread_consumed_tokens == 0
        assert user.total_credits_spent == 0
        assert billing.status == ThreadTurnBillingStatus.RELEASED.value
        assert billing.release_reason == "thread deleted by user"
        assert billing.transaction_id is None
        assert billing.user_message_id is None
        assert await session.get(Thread, billing_scenario.thread_id) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.user_id == billing_scenario.user_id)
            )
        ) == 0
