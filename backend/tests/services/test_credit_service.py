"""Tests for DataService-backed credit billing behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio

from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditSummaryPayload,
)
from src.services.credit_service import CreditService


class FakeCreditClient:
    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.reserved_balances: dict[str, int] = {}
        self.transactions: list[SimpleNamespace] = []
        self._counter = 0
        self._idempotency_index: dict[tuple[str, str, str], SimpleNamespace] = {}
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
            version=1,
            config={
                "input_weight": 0.3,
                "output_weight": 1,
                "credits_per_1k_weighted_tokens": 0.2,
                "min_chat_credits": 0,
                "free_tokens": 100000,
                "max_overdraft_credits": 100,
            },
        )

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
                mission_policy_id="thread" if transaction_type == "thread_token_consume" else "deep_research",
                workspace_id=None,
                task_id=None,
                admin_id=None,
                metadata=metadata,
                created_at=None,
            )
        )

    async def get_credit_balance(self, user_id: str) -> int | None:
        return self.balances.get(user_id)

    async def get_pricing_policy(self, policy_id_or_key: str):
        for policy in (self.global_policy, self.model_policy):
            if policy_id_or_key in {policy.id, policy.policy_key}:
                return policy
        return None

    async def resolve_model_usage_pricing(self, model_id: str):
        if model_id != "gpt-4o":
            raise ValueError(f"Enabled model catalog entry {model_id!r} is required")
        return SimpleNamespace(
            model_id=model_id,
            model_policy=self.model_policy,
            global_policy=self.global_policy,
        )

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

    async def get_credit_summary(self, user_id: str) -> CreditSummaryPayload | None:
        if user_id not in self.balances:
            return None
        return CreditSummaryPayload(
            credits=self.balances[user_id],
            reserved_credits=self.reserved_balances.get(user_id, 0),
            spendable_credits=self.balances[user_id] - self.reserved_balances.get(user_id, 0),
            total_earned=0,
            total_spent=0,
        )

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
            mission_policy_id=command.mission_policy_id,
            mission_id=command.mission_id,
            operation_key=command.operation_key,
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
            mission_policy_id=None,
            mission_id=None,
            operation_key=None,
            workspace_id=None,
            task_id=None,
            admin_id=command.admin_id,
            metadata=dict(command.metadata),
            created_at=None,
        )
        self.transactions.append(tx)
        return tx

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
                "min_mission_model_credits": 10,
                "max_overdraft_credits": 100,
                "free_tokens": 0,
            },
        )
        self.bound_model_policy = SimpleNamespace(
            id="bound-model-policy",
            policy_key="deepseek-bound-policy",
            policy_kind="model_usage",
            enabled=True,
            version=5,
            config={
                "input_weight": 0.2,
                "output_weight": 2,
                "credits_per_1k_weighted_tokens": 10,
                "min_chat_credits": 7,
                "min_mission_model_credits": 13,
                "max_overdraft_credits": 100,
                "free_tokens": 0,
            },
        )
        self.mission_policies: list[SimpleNamespace] = []

    async def get_pricing_policy(self, policy_id_or_key: str):
        if policy_id_or_key in {"global-credit", self.global_policy.id}:
            return self.global_policy
        if policy_id_or_key in {"gpt-4o", self.model_policy.id}:
            return self.model_policy
        if policy_id_or_key in {"deepseek-bound-policy", self.bound_model_policy.id}:
            return self.bound_model_policy
        return None

    async def resolve_model_usage_pricing(self, model_id: str):
        if model_id == "gpt-4o":
            model_policy = self.model_policy
        elif model_id == "deepseek-v3":
            model_policy = self.bound_model_policy
        else:
            raise ValueError(f"Enabled model catalog entry {model_id!r} is required")
        return SimpleNamespace(
            model_id=model_id,
            model_policy=model_policy,
            global_policy=self.global_policy,
        )

    async def list_pricing_policies(
        self,
        *,
        policy_kind: str | None = None,
        enabled_only: bool = False,
    ):
        rows = [
            self.global_policy,
            self.model_policy,
            self.bound_model_policy,
            *self.mission_policies,
        ]
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
async def test_consume_for_thread_usage_rejects_model_without_pricing_binding(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=20)
    pricing_credit_client.seed_consumption(
        user_id="user-1",
        transaction_type="thread_token_consume",
        amount=0,
        total_tokens=100000,
        balance_after=20,
    )

    with pytest.raises(ValueError, match="model catalog entry"):
        await pricing_credit_service.consume_for_thread_usage(
            user_id="user-1",
            token_usage={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
            model_name="unpriced-model",
            thread_id="thread-1",
        )

    assert await pricing_credit_service.get_balance("user-1") == 20


@pytest.mark.asyncio
async def test_consume_for_thread_usage_prefers_runtime_model_bound_pricing_policy(
    pricing_credit_client: PricingAwareFakeCreditClient,
    pricing_credit_service: CreditService,
) -> None:
    pricing_credit_client.add_user(credits=20)

    result = await pricing_credit_service.consume_for_thread_usage(
        user_id="user-1",
        token_usage={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        model_name="deepseek-v3",
        thread_id="thread-1",
    )

    assert result.credits_charged == 12
    assert await pricing_credit_service.get_balance("user-1") == 8

    tx = next(tx for tx in pricing_credit_client.transactions if tx.id == result.transaction_id)
    assert tx.metadata["policy"]["policy_key"] == "deepseek-bound-policy"
    assert tx.metadata["policy"]["version"] == 5
    assert tx.metadata["pricing_breakdown"]["weighted_tokens"] == 1200


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

    assert await credit_service.can_start_thread_turn("user-1", model_name="gpt-4o") is False


@pytest.mark.asyncio
async def test_user_credit_history_sanitizes_internal_token_metadata(
    fake_credit_client: FakeCreditClient,
    credit_service: CreditService,
) -> None:
    fake_credit_client.add_user(credits=10)
    fake_credit_client.transactions.append(
        SimpleNamespace(
            id="mission-settlement-1",
            user_id="user-1",
            transaction_type="workflow_consume",
            amount=-2,
            balance_after=8,
            description="mission settlement",
            mission_policy_id="deep_research",
            mission_id="mission-1",
            operation_key=None,
            workspace_id=None,
            task_id=None,
            admin_id=None,
            metadata={
                "type": "mission_token_billing",
                "credits_charged": 2,
                "token_usage": {"total_tokens": 15000},
                "billable_tokens": 15000,
                "policy": {"internal": True},
                "idempotency_key": "mission:mission-1",
            },
            created_at=None,
        )
    )

    items, total = await credit_service.get_history(user_id="user-1")

    assert total == 1
    assert items[0]["metadata"]["type"] == "mission_token_billing"
    assert items[0]["metadata"]["credits_charged"] == 2
    assert "token_usage" not in items[0]["metadata"]
    assert "billable_tokens" not in items[0]["metadata"]
    assert "policy" not in items[0]["metadata"]
    assert "idempotency_key" not in items[0]["metadata"]


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
    assert await credit_service.can_start_thread_turn("user-1", model_name="gpt-4o") is False


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
