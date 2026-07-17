"""Lifecycle tests for atomic chat-turn authorization and settlement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contracts.billing import ThreadTurnBillingStatus
from src.contracts.model_usage import ModelUsage
from src.database.models.thread_turn_billing import ThreadTurnBilling
from src.dataservice.common.errors import (
    CreditOverdraftLimitError,
    DataServiceConflictError,
    DataServiceValidationError,
)
from src.dataservice.domains.conversation.contracts import (
    ConversationBlockRecord,
    ConversationMessageRecord,
)
from src.dataservice.domains.thread_turn_billing.service import (
    ThreadTurnBillingService,
)
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
)
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnAuthorizePayload,
    ThreadTurnCompletePayload,
    ThreadTurnReconcilePayload,
    ThreadTurnReleaseByKeyPayload,
    ThreadTurnRollbackPayload,
)

NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC)


def test_thread_turn_billing_indexes_cover_query_and_foreign_key_paths() -> None:
    index_names = {index.name for index in ThreadTurnBilling.__table__.indexes}

    assert index_names == {
        "ix_thread_turn_billings_authorized_expiry",
        "ix_thread_turn_billings_thread_id",
        "ix_thread_turn_billings_user_id",
        "ix_thread_turn_billings_workspace_id",
    }


def test_thread_turn_billing_constraints_bind_money_usage_and_terminal_state() -> None:
    constraint_names = {
        constraint.name for constraint in ThreadTurnBilling.__table__.constraints
    }

    assert {
        "ck_thread_turn_billings_nonnegative_money",
        "ck_thread_turn_billings_nonnegative_usage",
        "ck_thread_turn_billings_state_timestamps",
        "ck_thread_turn_billings_status",
        "ck_thread_turn_billings_transaction_state",
        "ck_thread_turn_billings_usage_state",
    } <= constraint_names


def test_thread_turn_billing_keeps_a_soft_thread_audit_reference() -> None:
    thread_column = ThreadTurnBilling.__table__.c.thread_id
    transaction_fk = next(iter(ThreadTurnBilling.__table__.c.transaction_id.foreign_keys))

    assert thread_column.foreign_keys == set()
    assert transaction_fk.ondelete == "RESTRICT"


class _FakeBillingRepository:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}

    async def database_now(self) -> datetime:
        return NOW

    def create(self, values: dict) -> SimpleNamespace:
        row = SimpleNamespace(
            assistant_message_id=None,
            transaction_id=None,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            total_tokens=0,
            settled_at=None,
            released_at=None,
            release_reason=None,
            created_at=NOW,
            updated_at=NOW,
            **values,
        )
        self.rows[row.id] = row
        return row

    async def get_for_update(self, billing_id: str) -> SimpleNamespace | None:
        return self.rows.get(billing_id)

    async def get_by_idempotency_key_for_update(
        self,
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        return next(
            (
                row
                for row in self.rows.values()
                if row.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_expired_authorizations(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[tuple[str, str]]:
        return [
            (row.id, row.user_id)
            for row in self.rows.values()
            if row.status == ThreadTurnBillingStatus.AUTHORIZED.value
            and row.expires_at <= now
        ][:limit]

    async def list_authorized_for_thread_for_update(
        self,
        thread_id: str,
    ) -> list[SimpleNamespace]:
        return [
            row
            for row in self.rows.values()
            if row.thread_id == thread_id
            and row.status == ThreadTurnBillingStatus.AUTHORIZED.value
        ]

    async def list_expired_for_user_for_update(
        self,
        *,
        user_id: str,
        billing_ids: list[str],
        now: datetime,
    ) -> list[SimpleNamespace]:
        return [
            row
            for row in self.rows.values()
            if row.id in billing_ids
            and row.user_id == user_id
            and row.status == ThreadTurnBillingStatus.AUTHORIZED.value
            and row.expires_at <= now
        ]


class _FakeCreditRepository:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user
        self.transactions: list[SimpleNamespace] = []

    async def get_user_for_update(self, user_id: str) -> SimpleNamespace | None:
        return self.user if user_id == self.user.id else None

    def create_credit_transaction(self, values: dict) -> SimpleNamespace:
        transaction = SimpleNamespace(
            id=f"transaction-{len(self.transactions) + 1}",
            **values,
        )
        self.transactions.append(transaction)
        return transaction


class _FakeConversationRepository:
    def __init__(self) -> None:
        self.thread = SimpleNamespace(
            id="thread-1",
            user_id="user-1",
            workspace_id="workspace-1",
            model="gpt-5.6-terra",
        )
        self.deleted = False

    async def lock_thread(self, thread_id: str) -> None:
        assert thread_id == self.thread.id

    async def get_owned_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> SimpleNamespace | None:
        if thread_id == self.thread.id and user_id == self.thread.user_id:
            return self.thread
        return None

    async def delete_thread(self, thread: SimpleNamespace) -> None:
        assert thread is self.thread
        self.deleted = True


class _FakeConversationService:
    def __init__(self) -> None:
        self.repository = _FakeConversationRepository()
        self.messages: list[ConversationMessageRecord] = []

    async def append_message(self, command) -> SimpleNamespace:  # noqa: ANN001
        message_id = f"message-{len(self.messages) + 1}"
        blocks = [
            ConversationBlockRecord(
                id=f"block-{message_id}-{index}",
                message_id=message_id,
                thread_id=command.thread_id,
                block_type=str(block.get("kind") or "text"),
                sequence_index=index,
                payload_json=dict(block),
            )
            for index, block in enumerate(command.blocks)
        ]
        record = ConversationMessageRecord(
            id=message_id,
            thread_id=command.thread_id,
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            role=command.role,
            content=command.content,
            sequence_index=len(self.messages),
            timestamp=command.timestamp or NOW,
            metadata_json=dict(command.metadata),
            blocks=blocks,
            created_at=NOW,
            updated_at=NOW,
        )
        self.messages.append(record)
        return SimpleNamespace(id=record.id)

    async def get_message_record(
        self,
        message_id: str,
    ) -> ConversationMessageRecord | None:
        return next(
            (message for message in self.messages if message.id == message_id),
            None,
        )

    async def delete_trailing_user_message(
        self,
        *,
        thread_id: str,
        user_id: str,
        expected_message_id: str,
    ) -> bool:
        if not self.messages:
            return False
        message = self.messages[-1]
        if (
            message.thread_id != thread_id
            or message.user_id != user_id
            or message.id != expected_message_id
            or message.role != "user"
        ):
            return False
        self.messages.pop()
        return True


class _FakePricingResolver:
    def __init__(self) -> None:
        self.model_policy = SimpleNamespace(
            id="pricing-model",
            policy_key="model-terra",
            version=3,
            config_json={
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
            },
        )

    async def resolve_model_usage(self, model_id: str) -> SimpleNamespace:
        assert model_id == "gpt-5.6-terra"
        return self.model_policy

    async def resolve_global_credit(self) -> None:
        return None


def _service(*, credits: int = 10) -> tuple[
    ThreadTurnBillingService,
    SimpleNamespace,
    _FakeBillingRepository,
    _FakeCreditRepository,
    _FakeConversationService,
]:
    user = SimpleNamespace(
        id="user-1",
        credits=credits,
        reserved_credits=0,
        thread_consumed_tokens=0,
        reserved_thread_free_tokens=0,
        total_credits_spent=0,
    )
    session = SimpleNamespace(
        flush=AsyncMock(),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    service = ThreadTurnBillingService(session, autocommit=False)  # type: ignore[arg-type]
    billings = _FakeBillingRepository()
    credit = _FakeCreditRepository(user)
    conversation = _FakeConversationService()
    service.repository = billings  # type: ignore[assignment]
    service.credits = credit  # type: ignore[assignment]
    service.conversation = conversation  # type: ignore[assignment]
    service.pricing = _FakePricingResolver()  # type: ignore[assignment]
    return service, user, billings, credit, conversation


def _authorize(
    *,
    key: str = "chat-turn:run-1",
    content: str = "梳理联邦学习研究空白",
) -> ThreadTurnAuthorizePayload:
    return ThreadTurnAuthorizePayload(
        idempotency_key=key,
        model_id="gpt-5.6-terra",
        user_message=ConversationMessageCreatePayload(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="workspace-1",
            role="user",
            content=content,
            sequence_index=0,
            timestamp=NOW,
            metadata={"surface": "chat"},
        ),
    )


@pytest.mark.asyncio
async def test_authorization_atomically_holds_credit_and_persists_user_message() -> None:
    service, user, _billings, _credit, conversation = _service()

    result = await service.authorize(_authorize())

    assert result.created is True
    assert result.billing.status is ThreadTurnBillingStatus.AUTHORIZED
    assert result.user_message is not None
    assert result.user_message.id == "message-1"
    assert user.credits == 10
    assert user.reserved_credits == 6
    assert conversation.messages[0].metadata_json["billing_authorization_id"]


@pytest.mark.asyncio
async def test_release_by_idempotency_key_compensates_lost_authorization_response() -> None:
    service, user, _billings, _credit, _conversation = _service()
    authorized = await service.authorize(_authorize(key="lost-response"))
    command = ThreadTurnReleaseByKeyPayload(
        user_id="user-1",
        idempotency_key="lost-response",
        reason="authorization response unavailable after retry",
    )

    released = await service.release_by_idempotency_key(command)
    replayed = await service.release_by_idempotency_key(command)

    assert released.billing is not None
    assert released.billing.id == authorized.billing.id
    assert released.billing.status is ThreadTurnBillingStatus.RELEASED
    assert replayed.billing == released.billing
    assert user.reserved_credits == 0
    assert user.reserved_thread_free_tokens == 0


@pytest.mark.asyncio
async def test_release_by_unknown_idempotency_key_is_an_idempotent_noop() -> None:
    service, user, _billings, _credit, _conversation = _service()

    result = await service.release_by_idempotency_key(
        ThreadTurnReleaseByKeyPayload(
            user_id="user-1",
            idempotency_key="not-committed",
            reason="authorization response unavailable after retry",
        )
    )

    assert result.billing is None
    assert user.reserved_credits == 0
    assert user.reserved_thread_free_tokens == 0


@pytest.mark.asyncio
async def test_concurrent_authorization_cannot_spend_the_same_capacity_twice() -> None:
    service, user, _billings, _credit, conversation = _service()
    await service.authorize(_authorize())

    with pytest.raises(CreditOverdraftLimitError):
        await service.authorize(_authorize(key="chat-turn:run-2"))

    assert user.reserved_credits == 6
    assert len(conversation.messages) == 1


@pytest.mark.asyncio
async def test_exact_settlement_releases_hold_and_replays_without_double_charge() -> None:
    service, user, _billings, credit, conversation = _service()
    authorized = await service.authorize(_authorize())
    completion = ThreadTurnCompletePayload(
        user_id="user-1",
        assistant_message=ConversationMessageCreatePayload(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="workspace-1",
            role="assistant",
            content="可优先研究异构数据下的联邦 LoRA。",
            sequence_index=1,
            timestamp=NOW,
            blocks=[{"kind": "text", "content": "研究建议"}],
            metadata={"source": "workspace_agent"},
        ),
        token_usage=ModelUsage(
            input_tokens=1_000,
            cached_input_tokens=100,
            output_tokens=500,
            reasoning_tokens=200,
            total_tokens=1_500,
        ),
    )

    settled = await service.complete(authorized.billing.id, completion)
    replayed = await service.complete(authorized.billing.id, completion)

    assert settled.billing.status is ThreadTurnBillingStatus.SETTLED
    assert replayed.assistant_message.id == settled.assistant_message.id
    assert user.reserved_credits == 0
    assert user.thread_consumed_tokens == 1_500
    assert user.credits == 5
    assert len(credit.transactions) == 1
    assert credit.transactions[0].idempotency_key == (
        f"thread-turn:{authorized.billing.id}"
    )
    assert len(conversation.messages) == 2


@pytest.mark.asyncio
async def test_settlement_never_charges_more_than_the_authorized_hold() -> None:
    service, user, _billings, _credit, _conversation = _service()
    authorized = await service.authorize(_authorize())

    settled = await service.complete(
        authorized.billing.id,
        ThreadTurnCompletePayload(
            user_id="user-1",
            assistant_message=ConversationMessageCreatePayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="workspace-1",
                role="assistant",
                content="长回答",
                sequence_index=1,
                timestamp=NOW,
            ),
            token_usage=ModelUsage(output_tokens=5_000, total_tokens=5_000),
        ),
    )

    assert authorized.billing.reserved_credits == 6
    assert settled.billing.settled_credits == 6
    assert settled.billing_metadata["uncapped_credits"] == 30
    assert settled.billing_metadata["charge_capped"] is True
    assert user.credits == 4


@pytest.mark.asyncio
async def test_completion_rejects_missing_model_usage() -> None:
    service, _user, _billings, _credit, _conversation = _service()
    authorized = await service.authorize(_authorize())

    with pytest.raises(DataServiceValidationError, match="non-zero model usage"):
        await service.complete(
            authorized.billing.id,
            ThreadTurnCompletePayload(
                user_id="user-1",
                assistant_message=ConversationMessageCreatePayload(
                    thread_id="thread-1",
                    user_id="user-1",
                    workspace_id="workspace-1",
                    role="assistant",
                    content="不应保存",
                    sequence_index=1,
                    timestamp=NOW,
                ),
                token_usage=ModelUsage(),
            ),
        )


@pytest.mark.asyncio
async def test_completion_cannot_settle_after_authorization_expiry() -> None:
    service, user, billings, credit, conversation = _service()
    authorized = await service.authorize(_authorize())
    billings.rows[authorized.billing.id].expires_at = NOW - timedelta(seconds=1)

    with pytest.raises(DataServiceConflictError, match="has expired"):
        await service.complete(
            authorized.billing.id,
            ThreadTurnCompletePayload(
                user_id="user-1",
                assistant_message=ConversationMessageCreatePayload(
                    thread_id="thread-1",
                    user_id="user-1",
                    workspace_id="workspace-1",
                    role="assistant",
                    content="too late",
                    sequence_index=1,
                    timestamp=NOW,
                ),
                token_usage=ModelUsage(input_tokens=1, total_tokens=1),
            ),
        )

    assert user.reserved_credits == authorized.billing.reserved_credits
    assert credit.transactions == []
    assert len(conversation.messages) == 1


@pytest.mark.asyncio
async def test_authorization_idempotency_replays_settled_assistant() -> None:
    service, _user, _billings, _credit, _conversation = _service()
    authorized = await service.authorize(_authorize())
    await service.complete(
        authorized.billing.id,
        ThreadTurnCompletePayload(
            user_id="user-1",
            assistant_message=ConversationMessageCreatePayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="workspace-1",
                role="assistant",
                content="完成",
                sequence_index=1,
                timestamp=NOW,
            ),
            token_usage=ModelUsage(input_tokens=1, total_tokens=1),
        ),
    )

    replay = await service.authorize(_authorize())

    assert replay.created is False
    assert replay.billing.status is ThreadTurnBillingStatus.SETTLED
    assert replay.assistant_message is not None
    assert replay.assistant_message.content == "完成"
    with pytest.raises(DataServiceConflictError, match="different request"):
        await service.authorize(_authorize(content="复用同一个键但修改消息"))


@pytest.mark.asyncio
async def test_rollback_releases_hold_without_erasing_billing_audit() -> None:
    service, user, billings, _credit, conversation = _service()
    authorized = await service.authorize(_authorize())

    rolled_back = await service.rollback(
        authorized.billing.id,
        ThreadTurnRollbackPayload(
            user_id="user-1",
            reason="user replaced the in-flight turn",
        ),
    )

    assert rolled_back.message_rolled_back is True
    assert rolled_back.billing.status is ThreadTurnBillingStatus.RELEASED
    assert rolled_back.billing.user_message_id is None
    assert user.reserved_credits == 0
    assert conversation.messages == []
    assert authorized.billing.id in billings.rows
    with pytest.raises(DataServiceConflictError, match="no longer active"):
        await service.authorize(_authorize())


@pytest.mark.asyncio
async def test_thread_delete_releases_hold_and_preserves_billing_audit() -> None:
    service, user, billings, _credit, conversation = _service()
    authorized = await service.authorize(_authorize())

    deleted = await service.delete_thread(
        thread_id="thread-1",
        user_id="user-1",
    )

    assert deleted is True
    assert user.reserved_credits == 0
    assert billings.rows[authorized.billing.id].status == (
        ThreadTurnBillingStatus.RELEASED.value
    )
    assert billings.rows[authorized.billing.id].release_reason == (
        "thread deleted by user"
    )
    assert conversation.repository.deleted is True
    assert authorized.billing.id in billings.rows


@pytest.mark.asyncio
async def test_expired_authorization_reconciler_releases_all_holds() -> None:
    service, user, billings, _credit, _conversation = _service()
    authorized = await service.authorize(_authorize())
    billings.rows[authorized.billing.id].expires_at = NOW - timedelta(seconds=1)

    result = await service.reconcile_expired(
        ThreadTurnReconcilePayload(now=NOW, limit=100)
    )

    assert result.expired_billing_ids == [authorized.billing.id]
    assert user.reserved_credits == 0
    assert billings.rows[authorized.billing.id].status == (
        ThreadTurnBillingStatus.EXPIRED.value
    )
