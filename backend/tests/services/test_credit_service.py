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
from src.services.billing_policy import OperationBillingPolicy, TokenBillingPolicy
from src.services.credit_service import CreditService


class FakeCreditClient:
    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.reserved_balances: dict[str, int] = {}
        self.transactions: list[SimpleNamespace] = []
        self.reservations: dict[str, SimpleNamespace] = {}
        self._counter = 0
        self._refunded: set[str] = set()
        self._idempotency_index: dict[tuple[str, str, str], SimpleNamespace] = {}
        self._reservation_idempotency_index: dict[tuple[str, str, str], SimpleNamespace] = {}

    def add_user(self, user_id: str = "user-1", *, credits: int = 10) -> None:
        self.balances[user_id] = credits
        self.reserved_balances[user_id] = 0

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
        idempotency_key = str(command.metadata.get("idempotency_key") or "").strip()
        if idempotency_key:
            existing = self._idempotency_index.get(
                (command.user_id, command.transaction_type, idempotency_key)
            )
            if existing is not None:
                return existing, before
        after = before - command.amount
        self.balances[command.user_id] = after
        self._counter += 1
        tx = SimpleNamespace(
            id=f"tx-{self._counter}",
            user_id=command.user_id,
            transaction_type=command.transaction_type,
            amount=-command.amount,
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
        if idempotency_key:
            self._idempotency_index[
                (command.user_id, command.transaction_type, idempotency_key)
            ] = tx
        return tx, before

    async def refund_credit_consumption(self, command: CreditRefundPayload):
        original = next(tx for tx in self.transactions if tx.id == command.original_transaction_id)
        refund_amount = abs(int(original.amount))
        self._refunded.add(original.id)
        self.balances[command.user_id] = self.balances.get(command.user_id, 0) + refund_amount
        self._counter += 1
        tx = SimpleNamespace(
            id=f"refund-{self._counter}",
            user_id=command.user_id,
            transaction_type="refund",
            amount=refund_amount,
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

    async def create_credit_reservation(self, command):
        before = self.balances.get(command.user_id)
        if before is None:
            raise ValueError("User not found")
        idempotency_key = str(command.idempotency_key)
        key = (command.user_id, command.scope, idempotency_key)
        existing = self._reservation_idempotency_index.get(key)
        if existing is not None:
            return existing
        spendable = before - self.reserved_balances.get(command.user_id, 0)
        if command.reserved_credits > spendable:
            raise ValueError("insufficient spendable credits")
        self.reserved_balances[command.user_id] = (
            self.reserved_balances.get(command.user_id, 0) + command.reserved_credits
        )
        self._counter += 1
        reservation = SimpleNamespace(
            id=f"reservation-{self._counter}",
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            execution_id=command.execution_id,
            node_id=command.node_id,
            scope=command.scope,
            status="reserved",
            reserved_credits=command.reserved_credits,
            settled_credits=0,
            transaction_id=None,
            idempotency_key=command.idempotency_key,
            expires_at=command.expires_at,
            metadata=dict(command.metadata),
            created_at=None,
            updated_at=None,
        )
        self.reservations[reservation.id] = reservation
        self._reservation_idempotency_index[key] = reservation
        return reservation

    async def settle_credit_reservation(self, reservation_id: str, command):
        reservation = self.reservations[reservation_id]
        if reservation.status != "reserved":
            tx = next((tx for tx in self.transactions if tx.id == reservation.transaction_id), None)
            return reservation, tx
        charge = min(command.settled_credits, reservation.reserved_credits)
        self.reserved_balances[reservation.user_id] -= reservation.reserved_credits
        self.balances[reservation.user_id] -= charge
        self._counter += 1
        tx = SimpleNamespace(
            id=f"tx-{self._counter}",
            user_id=reservation.user_id,
            transaction_type="workflow_consume",
            amount=-charge,
            balance_after=self.balances[reservation.user_id],
            description=command.description,
            feature_id=command.feature_id,
            workspace_id=reservation.workspace_id,
            task_id=command.task_id,
            admin_id=None,
            metadata={"reservation_id": reservation_id, **dict(command.metadata)},
            created_at=None,
        )
        reservation.status = "settled"
        reservation.settled_credits = charge
        reservation.transaction_id = tx.id
        self.transactions.append(tx)
        return reservation, tx

    async def release_credit_reservation(self, reservation_id: str, *, reason: str | None = None):
        reservation = self.reservations[reservation_id]
        if reservation.status == "reserved":
            self.reserved_balances[reservation.user_id] -= reservation.reserved_credits
            reservation.status = "released"
            reservation.metadata["release_reason"] = reason
        return reservation


class PricingAwareFakeCreditClient(FakeCreditClient):
    def __init__(self) -> None:
        super().__init__()
        self.global_policy = SimpleNamespace(
            id="global-policy",
            policy_key="global-credit",
            policy_kind="global_credit",
            enabled=True,
            version=1,
            config={"credits_per_cny": 10, "usd_to_cny": 7.3},
        )
        self.model_policy = SimpleNamespace(
            id="model-policy",
            policy_key="gpt-4o",
            policy_kind="model_usage",
            enabled=True,
            version=3,
            config={
                "input_weight": 0.3,
                "output_weight": 1,
                "credits_per_1k_weighted_tokens": 6,
                "min_chat_credits": 3,
                "min_feature_model_credits": 10,
                "max_overdraft_credits": 100,
            },
        )

    async def get_pricing_policy(self, policy_id_or_key: str):
        if policy_id_or_key in {"global-credit", self.global_policy.id}:
            return self.global_policy
        if policy_id_or_key in {"gpt-4o", self.model_policy.id}:
            return self.model_policy
        return None

    async def list_pricing_policies(
        self,
        *,
        policy_kind: str | None = None,
        enabled_only: bool = False,
    ):
        rows = [self.global_policy, self.model_policy]
        if policy_kind is not None:
            rows = [row for row in rows if row.policy_kind == policy_kind]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows


@pytest_asyncio.fixture
async def fake_credit_client() -> FakeCreditClient:
    return FakeCreditClient()


@pytest_asyncio.fixture
async def credit_service(fake_credit_client: FakeCreditClient) -> CreditService:
    return CreditService(dataservice=fake_credit_client)


@pytest_asyncio.fixture
async def pricing_credit_client() -> PricingAwareFakeCreditClient:
    return PricingAwareFakeCreditClient()


@pytest_asyncio.fixture
async def pricing_credit_service(pricing_credit_client: PricingAwareFakeCreditClient) -> CreditService:
    return CreditService(dataservice=pricing_credit_client)


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
async def test_consume_for_thread_usage_uses_pricing_policy_weighted_tokens(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=20)

    result = await pricing_credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.free_tokens_applied == 0
    assert result.billable_tokens == 1500
    assert result.credits_charged == 5
    assert result.charged is True
    assert await pricing_credit_service.get_balance("user-1") == 15

    tx = next(tx for tx in pricing_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["policy"]["policy_key"] == "gpt-4o"
    assert tx.metadata["policy"]["version"] == 3
    assert tx.metadata["pricing_breakdown"]["weighted_tokens"] == 800
    assert tx.metadata["credits_charged"] == 5


@pytest.mark.asyncio
async def test_consume_for_thread_usage_applies_pricing_policy_chat_minimum(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=20)

    result = await pricing_credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.credits_charged == 3
    assert await pricing_credit_service.get_balance("user-1") == 17


@pytest.mark.asyncio
async def test_consume_for_feature_usage_applies_pricing_policy_feature_minimum(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=20)

    result = await pricing_credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
        task_id="task-1",
    )

    assert result.credits_charged == 10
    assert await pricing_credit_service.get_balance("user-1") == 10


@pytest.mark.asyncio
async def test_consume_for_thread_usage_applies_pricing_policy_raw_cost_guard(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=50)
    pricing_credit_client.model_policy.config = {
        **pricing_credit_client.model_policy.config,
        "credits_per_1k_weighted_tokens": 1,
        "cost_guard_multiplier": 20,
        "raw_cost": {"input_usd_per_1m": 1, "output_usd_per_1m": 10},
    }

    result = await pricing_credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 1000, "output_tokens": 1000, "total_tokens": 2000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.credits_charged == 17
    tx = next(tx for tx in pricing_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["pricing_breakdown"]["raw_cost_guard_credits"] == 17


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
async def test_can_start_sandbox_operation_blocks_when_balance_empty(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=0)

    assert await credit_service.can_start_sandbox_operation("user-1", "run_python") is False


@pytest.mark.asyncio
async def test_consume_for_sandbox_operation_charges_fixed_credits(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)

    result = await credit_service.consume_for_sandbox_operation(
        user_id="user-1",
        operation="run_python",
        workspace_id="ws-1",
        task_id="exec-1",
        node_id="phase__sandbox",
    )

    assert result.operation == "run_python"
    assert result.credits_charged == 1
    assert result.charged is True
    assert result.balance_after == 9
    assert await credit_service.get_balance("user-1") == 9

    tx = next(tx for tx in fake_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.transaction_type == "workflow_consume"
    assert tx.feature_id == "sandbox.run_python"
    assert tx.workspace_id == "ws-1"
    assert tx.task_id == "exec-1"
    assert tx.metadata["type"] == "sandbox_operation_billing"
    assert tx.metadata["operation"] == "run_python"
    assert tx.metadata["credits_charged"] == 1
    assert tx.metadata["policy"]["max_overdraft_credits"] == 100
    assert tx.metadata["idempotency_key"] == "sandbox_operation_billing:exec-1:phase__sandbox:run_python"


@pytest.mark.asyncio
async def test_sandbox_operation_consumption_replays_by_execution_node_idempotency(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)

    first = await credit_service.consume_for_sandbox_operation(
        user_id="user-1",
        operation="run_python",
        workspace_id="ws-1",
        task_id="exec-1",
        node_id="phase__sandbox",
    )
    second = await credit_service.consume_for_sandbox_operation(
        user_id="user-1",
        operation="run_python",
        workspace_id="ws-1",
        task_id="exec-1",
        node_id="phase__sandbox",
    )

    workflow_transactions = [
        tx for tx in fake_credit_client.transactions
        if tx.transaction_type == "workflow_consume"
    ]
    assert second.transaction_id == first.transaction_id
    assert second.balance_after == first.balance_after
    assert len(workflow_transactions) == 1
    assert await credit_service.get_balance("user-1") == 9


@pytest.mark.asyncio
async def test_sandbox_operation_billing_disabled_records_no_transaction(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credit_client.add_user(credits=0)
    monkeypatch.setattr(
        CreditService,
        "get_sandbox_billing_policy",
        staticmethod(
            lambda: OperationBillingPolicy(
                enabled=False,
                run_python_credits=1,
                max_overdraft_credits=100,
            )
        ),
    )

    assert await credit_service.can_start_sandbox_operation("user-1", "run_python") is True
    result = await credit_service.consume_for_sandbox_operation(
        user_id="user-1",
        operation="run_python",
        task_id="exec-1",
        node_id="phase__sandbox",
    )

    assert result.charged is False
    assert result.credits_charged == 0
    assert fake_credit_client.transactions == []


@pytest.mark.asyncio
async def test_user_credit_history_sanitizes_internal_token_metadata(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)
    await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 15000},
        task_id="exec-1",
    )

    items, total = await credit_service.get_history(user_id="user-1")

    assert total == 1
    assert items[0]["metadata"]["type"] == "feature_token_billing"
    assert items[0]["metadata"]["credits_charged"] == 2
    assert "token_usage" not in items[0]["metadata"]
    assert "billable_tokens" not in items[0]["metadata"]
    assert "policy" not in items[0]["metadata"]
    assert "idempotency_key" not in items[0]["metadata"]


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
async def test_thread_usage_consumption_sends_overdraft_policy(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=1)

    result = await credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"total_tokens": 120000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    tx = next(tx for tx in fake_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["policy"]["max_overdraft_credits"] == 100


@pytest.mark.asyncio
async def test_thread_usage_consumption_preserves_idempotency_key(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)

    result = await credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"total_tokens": 120000},
        model_name="gpt-4o",
        thread_id="thread-1",
        metadata={"idempotency_key": "thread_token_billing:msg-1"},
    )

    tx = next(tx for tx in fake_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["idempotency_key"] == "thread_token_billing:msg-1"


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
async def test_feature_usage_consumption_sends_overdraft_policy(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=1)

    result = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 15000},
        task_id="task-1",
    )

    tx = next(tx for tx in fake_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["policy"]["max_overdraft_credits"] == 100


@pytest.mark.asyncio
async def test_feature_usage_consumption_replays_by_task_id_idempotency(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)

    first = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 15000},
        task_id="exec-1",
    )
    second = await credit_service.consume_for_feature_usage(
        user_id="user-1",
        feature_id="deep_research",
        token_usage={"total_tokens": 15000},
        task_id="exec-1",
    )

    workflow_transactions = [
        tx for tx in fake_credit_client.transactions
        if tx.transaction_type == "workflow_consume"
    ]
    assert second.transaction_id == first.transaction_id
    assert second.historical_tokens_before == first.historical_tokens_before
    assert len(workflow_transactions) == 1
    assert await credit_service.get_balance("user-1") == 8
    assert await credit_service.get_consumed_feature_tokens("user-1") == 15000
    assert workflow_transactions[0].metadata["idempotency_key"] == "feature_token_billing:exec-1"


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


@pytest.mark.asyncio
async def test_reserve_for_feature_execution_delegates_to_dataservice(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=20)

    reservation = await credit_service.reserve_for_feature_execution(
        user_id="user-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        estimated_credits=12,
        metadata={"feature_id": "deep_research"},
    )

    assert reservation.reserved_credits == 12
    assert reservation.status == "reserved"
    assert fake_credit_client.reserved_balances["user-1"] == 12
    assert fake_credit_client.balances["user-1"] == 20


@pytest.mark.asyncio
async def test_settle_feature_reservation_charges_and_releases_remainder(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=20)
    reservation = await credit_service.reserve_for_feature_execution(
        user_id="user-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        estimated_credits=12,
    )

    settled, tx = await credit_service.settle_feature_reservation(
        reservation_id=reservation.id,
        settled_credits=8,
        feature_id="deep_research",
        task_id="exec-1",
        metadata={"actual_credits": 8},
    )

    assert settled.status == "settled"
    assert settled.settled_credits == 8
    assert settled.transaction_id == tx.id
    assert tx.metadata["reservation_id"] == reservation.id
    assert fake_credit_client.reserved_balances["user-1"] == 0
    assert fake_credit_client.balances["user-1"] == 12


@pytest.mark.asyncio
async def test_release_reservation_delegates_to_dataservice(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=20)
    reservation = await credit_service.reserve_for_sandbox_operation(
        user_id="user-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="node-1",
        operation="run_python",
        estimated_credits=5,
    )

    released = await credit_service.release_reservation(
        reservation.id,
        reason="platform failed",
    )

    assert released.status == "released"
    assert fake_credit_client.reserved_balances["user-1"] == 0
    assert fake_credit_client.balances["user-1"] == 20
    assert released.metadata["release_reason"] == "platform failed"
