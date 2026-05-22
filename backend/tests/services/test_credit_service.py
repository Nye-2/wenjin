"""Tests for DataService-backed credit billing behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio

from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditRefundPayload,
    CreditSummaryPayload,
)
from src.services.billing_policy import TokenBillingPolicy
from src.services.credit_service import CreditService


class FakeCreditClient:
    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.transactions: list[SimpleNamespace] = []
        self._counter = 0
        self._refunded: set[str] = set()

    def add_user(self, user_id: str = "user-1", *, credits: int = 10) -> None:
        self.balances[user_id] = credits

    def seed_consumption(
        self,
        *,
        user_id: str,
        transaction_type: str,
        amount: int,
        total_tokens: int,
        balance_after: int,
        metadata_type: str | None = None,
    ) -> None:
        metadata = {"token_usage": {"total_tokens": total_tokens}}
        if metadata_type:
            metadata["type"] = metadata_type
        self._counter += 1
        self.transactions.append(
            SimpleNamespace(
                id=f"seed-{self._counter}",
                user_id=user_id,
                transaction_type=transaction_type,
                amount=amount,
                balance_after=balance_after,
                description="seed tx",
                feature_id="thread" if transaction_type == "thread_token_consume" else "deep_research",
                workspace_id=None,
                task_id=None,
                admin_id=None,
                metadata=metadata,
                created_at=None,
            )
        )

    async def get_credit_balance(self, user_id: str) -> int | None:
        return self.balances.get(user_id)

    async def get_credit_summary(self, user_id: str) -> CreditSummaryPayload | None:
        if user_id not in self.balances:
            return None
        return CreditSummaryPayload(credits=self.balances[user_id], total_earned=0, total_spent=0)

    async def get_credit_history(
        self,
        *,
        user_id: str | None = None,
        transaction_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        rows = [
            tx
            for tx in self.transactions
            if (user_id is None or tx.user_id == user_id)
            and (transaction_type is None or tx.transaction_type == transaction_type)
        ]
        return SimpleNamespace(transactions=rows[offset : offset + limit], total=len(rows))

    async def get_credit_consumed_tokens(
        self,
        *,
        user_id: str,
        consume_type: str,
        metadata_type: str | None = None,
    ) -> int:
        total = 0
        for tx in self.transactions:
            if tx.id in self._refunded:
                continue
            if tx.user_id != user_id or tx.transaction_type != consume_type:
                continue
            if metadata_type and tx.metadata.get("type") != metadata_type:
                continue
            usage = tx.metadata.get("token_usage") or {}
            total += int(usage.get("total_tokens", 0) or 0)
        return total

    async def record_credit_consumption(self, command: CreditConsumptionCreatePayload):
        before = self.balances.get(command.user_id)
        if before is None:
            raise ValueError("User not found")
        after = before - command.amount
        self.balances[command.user_id] = after
        self._counter += 1
        tx = SimpleNamespace(
            id=f"tx-{self._counter}",
            user_id=command.user_id,
            transaction_type=command.transaction_type,
            amount=command.amount,
            balance_after=after,
            description=command.description,
            feature_id=command.feature_id,
            workspace_id=command.workspace_id,
            task_id=command.task_id,
            admin_id=None,
            metadata=dict(command.metadata),
            created_at=None,
        )
        self.transactions.append(tx)
        return tx, before

    async def refund_credit_consumption(self, command: CreditRefundPayload):
        original = next(tx for tx in self.transactions if tx.id == command.original_transaction_id)
        self._refunded.add(original.id)
        self.balances[command.user_id] = self.balances.get(command.user_id, 0) + int(original.amount)
        self._counter += 1
        tx = SimpleNamespace(
            id=f"refund-{self._counter}",
            user_id=command.user_id,
            transaction_type="refund",
            amount=int(original.amount),
            balance_after=self.balances[command.user_id],
            description=command.reason,
            feature_id=original.feature_id,
            workspace_id=original.workspace_id,
            task_id=command.task_id,
            admin_id=None,
            metadata={"original_transaction_id": original.id},
            created_at=None,
        )
        self.transactions.append(tx)
        return tx

    async def admin_adjust_credit(self, command: CreditAdminAdjustPayload):
        before = self.balances.get(command.target_user_id)
        if before is None:
            raise ValueError("User not found")
        after = before + command.amount
        self.balances[command.target_user_id] = after
        self._counter += 1
        tx = SimpleNamespace(
            id=f"admin-{self._counter}",
            user_id=command.target_user_id,
            transaction_type=command.transaction_type,
            amount=command.amount,
            balance_after=after,
            description=command.description,
            feature_id=None,
            workspace_id=None,
            task_id=None,
            admin_id=command.admin_id,
            metadata=dict(command.metadata),
            created_at=None,
        )
        self.transactions.append(tx)
        return tx


@pytest_asyncio.fixture
async def fake_credit_client() -> FakeCreditClient:
    return FakeCreditClient()


@pytest_asyncio.fixture
async def credit_service(fake_credit_client: FakeCreditClient) -> CreditService:
    return CreditService(dataservice=fake_credit_client)


@pytest.mark.asyncio
async def test_consume_for_thread_usage_applies_free_quota_before_charging(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)
    fake_credit_client.seed_consumption(
        user_id="user-1",
        transaction_type="thread_token_consume",
        amount=0,
        total_tokens=95000,
        balance_after=10,
    )

    result = await credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 6000, "output_tokens": 4000, "total_tokens": 10000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.free_tokens_applied == 5000
    assert result.billable_tokens == 5000
    assert result.credits_charged == 1
    assert result.historical_tokens_before == 95000
    assert result.historical_tokens_after == 105000
    assert result.charged is True
    assert await credit_service.get_balance("user-1") == 9


@pytest.mark.asyncio
async def test_can_start_thread_turn_blocks_when_free_quota_exhausted_and_balance_empty(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=0)
    fake_credit_client.seed_consumption(
        user_id="user-1",
        transaction_type="thread_token_consume",
        amount=0,
        total_tokens=100000,
        balance_after=0,
    )

    assert await credit_service.can_start_thread_turn("user-1") is False


@pytest.mark.asyncio
async def test_can_start_feature_task_blocks_when_balance_empty(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=0)

    assert await credit_service.can_start_feature_task("user-1") is False


@pytest.mark.asyncio
async def test_can_start_feature_task_allows_free_feature_quota(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credit_client.add_user(credits=0)
    monkeypatch.setattr(
        CreditService,
        "get_feature_billing_policy",
        staticmethod(
            lambda: TokenBillingPolicy(
                enabled=True,
                free_tokens=100000,
                tokens_per_credit=10000,
                max_overdraft_credits=100,
            )
        ),
    )
    fake_credit_client.seed_consumption(
        user_id="user-1",
        transaction_type="workflow_consume",
        amount=0,
        total_tokens=5000,
        balance_after=0,
        metadata_type="feature_token_billing",
    )

    assert await credit_service.can_start_feature_task("user-1") is True


@pytest.mark.asyncio
async def test_refund_consumption_releases_free_chat_tokens(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=3)

    result = await credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 4000, "output_tokens": 1000, "total_tokens": 5000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.transaction_id is not None
    assert result.credits_charged == 0
    assert await credit_service.get_consumed_thread_tokens("user-1") == 5000

    refund = await credit_service.refund_consumption(
        user_id="user-1",
        original_transaction_id=result.transaction_id,
        reason="chat persist failed",
    )

    assert refund is not None
    assert refund.amount == 0
    assert await credit_service.get_balance("user-1") == 3
    assert await credit_service.get_consumed_thread_tokens("user-1") == 0


@pytest.mark.asyncio
async def test_consume_for_thread_usage_allows_dataservice_atomic_overdraft(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=1)
    fake_credit_client.seed_consumption(
        user_id="user-1",
        transaction_type="thread_token_consume",
        amount=0,
        total_tokens=100000,
        balance_after=1,
    )

    result = await credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 15000, "output_tokens": 5000, "total_tokens": 20000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.credits_charged == 2
    assert result.balance_after == -1
    assert result.charged is True
    assert await credit_service.get_balance("user-1") == -1
    assert await credit_service.can_start_thread_turn("user-1") is False


@pytest.mark.asyncio
async def test_consume_for_feature_usage_charges_by_tokens(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)

    result = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"input_tokens": 12000, "output_tokens": 3000, "total_tokens": 15000},
        workspace_id="ws-1",
        task_id="task-1",
        metadata={"workspace_type": "thesis"},
    )

    assert result.billable_tokens == 15000
    assert result.credits_charged == 2
    assert result.charged is True
    assert await credit_service.get_balance("user-1") == 8
    assert await credit_service.get_consumed_feature_tokens("user-1") == 15000


@pytest.mark.asyncio
async def test_refund_consumption_releases_feature_tokens(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)
    result = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 15000},
        task_id="task-1",
    )

    assert result.transaction_id is not None
    refund = await credit_service.refund_consumption(
        user_id="user-1",
        original_transaction_id=result.transaction_id,
        reason="feature persist failed",
    )

    assert refund is not None
    assert refund.amount == 2
    assert await credit_service.get_balance("user-1") == 10
    assert await credit_service.get_consumed_feature_tokens("user-1") == 0


@pytest.mark.asyncio
async def test_refund_consumption_releases_free_feature_tokens(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credit_client.add_user(credits=10)
    monkeypatch.setattr(
        CreditService,
        "get_feature_billing_policy",
        staticmethod(
            lambda: TokenBillingPolicy(
                enabled=True,
                free_tokens=100000,
                tokens_per_credit=10000,
                max_overdraft_credits=100,
            )
        ),
    )

    result = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 5000},
        task_id="task-1",
    )

    assert result.transaction_id is not None
    assert result.credits_charged == 0
    assert await credit_service.get_consumed_feature_tokens("user-1") == 5000

    refund = await credit_service.refund_consumption(
        user_id="user-1",
        original_transaction_id=result.transaction_id,
        reason="feature persist failed",
    )

    assert refund is not None
    assert refund.amount == 0
    assert await credit_service.get_consumed_feature_tokens("user-1") == 0


@pytest.mark.asyncio
async def test_admin_deduct_keeps_direction_correct_for_negative_balances(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=-1)

    tx = await credit_service.admin_deduct(
        admin_id="admin-1",
        target_user_id="user-1",
        amount=5,
        description="manual adjustment",
    )

    assert tx.amount == -5
    assert tx.balance_after == -6
    assert tx.metadata["requested_amount"] == 5
    assert await credit_service.get_balance("user-1") == -6
