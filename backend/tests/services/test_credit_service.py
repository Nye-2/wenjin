"""Tests for the read-side credit facade and admin operations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditSummaryPayload,
)
from src.services.credit_service import CreditService


class FakeCreditClient:
    def __init__(self) -> None:
        self.balance = 0
        self.summary = CreditSummaryPayload(
            credits=0,
            reserved_credits=0,
            spendable_credits=0,
            thread_consumed_tokens=0,
            reserved_thread_free_tokens=0,
            total_earned=0,
            total_spent=0,
        )
        self.model_policy = SimpleNamespace(
            config={
                "free_tokens": 100_000,
                "max_overdraft_credits": 0,
                "chat_turn_token_reserve": 65_536,
                "chat_turn_max_credits": 100,
            }
        )
        self.global_policy = None
        self.transactions: list[SimpleNamespace] = []

    async def get_credit_balance(self, user_id: str) -> int | None:
        return self.balance if user_id == "user-1" else None

    async def get_credit_summary(self, user_id: str) -> CreditSummaryPayload | None:
        return self.summary if user_id == "user-1" else None

    async def resolve_model_usage_pricing(self, model_id: str) -> SimpleNamespace:
        if model_id != "gpt-5.6-terra":
            raise ValueError("Enabled model catalog entry is required")
        return SimpleNamespace(
            model_policy=self.model_policy,
            global_policy=self.global_policy,
        )

    async def get_credit_history(
        self,
        *,
        user_id: str | None = None,
        transaction_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SimpleNamespace:
        rows = [
            item
            for item in self.transactions
            if (user_id is None or item.user_id == user_id)
            and (
                transaction_type is None
                or item.transaction_type == transaction_type
            )
        ]
        return SimpleNamespace(
            transactions=rows[offset : offset + limit],
            total=len(rows),
        )

    async def admin_adjust_credit(
        self,
        command: CreditAdminAdjustPayload,
    ) -> SimpleNamespace:
        self.balance += command.amount
        return SimpleNamespace(
            id="tx-admin",
            amount=command.amount,
            balance_after=self.balance,
            metadata=dict(command.metadata),
        )


@pytest.mark.asyncio
async def test_capacity_preview_uses_projected_free_token_holds() -> None:
    client = FakeCreditClient()
    client.summary = client.summary.model_copy(
        update={"thread_consumed_tokens": 20_000}
    )
    service = CreditService(dataservice=client)

    assert await service.preview_thread_turn_capacity(
        "user-1",
        model_name="gpt-5.6-terra",
    )


@pytest.mark.asyncio
async def test_capacity_preview_requires_credit_hold_when_free_reserve_is_partial() -> None:
    client = FakeCreditClient()
    client.summary = client.summary.model_copy(
        update={"thread_consumed_tokens": 50_000}
    )
    service = CreditService(dataservice=client)

    assert not await service.preview_thread_turn_capacity(
        "user-1",
        model_name="gpt-5.6-terra",
    )


@pytest.mark.asyncio
async def test_capacity_preview_includes_spendable_balance_and_overdraft() -> None:
    client = FakeCreditClient()
    client.summary = client.summary.model_copy(
        update={
            "credits": 80,
            "spendable_credits": 80,
            "thread_consumed_tokens": 100_000,
        }
    )
    client.model_policy.config["max_overdraft_credits"] = 20
    service = CreditService(dataservice=client)

    assert await service.preview_thread_turn_capacity(
        "user-1",
        model_name="gpt-5.6-terra",
    )


@pytest.mark.asyncio
async def test_user_credit_history_hides_internal_billing_details() -> None:
    client = FakeCreditClient()
    client.transactions.append(
        SimpleNamespace(
            id="mission-settlement-1",
            user_id="user-1",
            transaction_type="workflow_consume",
            amount=-2,
            balance_after=8,
            description="mission settlement",
            mission_policy_id="sci.research",
            mission_id="mission-1",
            operation_key=None,
            workspace_id=None,
            task_id=None,
            admin_id=None,
            idempotency_key="reservation-settlement:reservation-1",
            metadata={
                "type": "mission_token_billing",
                "credits_charged": 2,
                "token_usage": {"total_tokens": 15_000},
                "policy": {"internal": True},
            },
            created_at=None,
        )
    )
    service = CreditService(dataservice=client)

    items, total = await service.get_history(user_id="user-1")

    assert total == 1
    assert items[0]["metadata"] == {
        "type": "mission_token_billing",
        "credits_charged": 2,
    }


@pytest.mark.asyncio
async def test_admin_deduct_preserves_signed_direction_below_zero() -> None:
    client = FakeCreditClient()
    client.balance = -1
    service = CreditService(dataservice=client)

    transaction = await service.admin_deduct(
        admin_id="admin-1",
        target_user_id="user-1",
        amount=5,
        description="manual adjustment",
    )

    assert transaction.amount == -5
    assert transaction.balance_after == -6
    assert transaction.metadata["requested_amount"] == 5
