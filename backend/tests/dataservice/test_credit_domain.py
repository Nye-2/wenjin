"""Tests for DataService credit domain behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.credit import CreditTransactionType
from src.dataservice.common.errors import CreditOverdraftLimitError
from src.dataservice.domains.credit.service import DataServiceCreditService


class _FakeCreditRepository:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user
        self.created_transactions: list[dict] = []
        self.idempotent_transactions: dict[tuple[str, CreditTransactionType, str], SimpleNamespace] = {}

    async def get_user_for_update(self, user_id: str) -> SimpleNamespace | None:
        if user_id != self.user.id:
            return None
        return self.user

    async def find_consumption_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type: CreditTransactionType,
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        return self.idempotent_transactions.get((user_id, transaction_type, idempotency_key))

    def create_credit_transaction(self, values: dict) -> SimpleNamespace:
        self.created_transactions.append(values)
        return SimpleNamespace(id="tx-1", **values)


@pytest.mark.asyncio
async def test_record_consumption_rejects_charge_beyond_overdraft_floor() -> None:
    """DataService should enforce max_overdraft_credits while holding the user lock."""
    user = SimpleNamespace(
        id="user-1",
        credits=1,
        total_credits_spent=0,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(CreditOverdraftLimitError, match="overdraft"):
        await service.record_consumption(
            user_id="user-1",
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=5,
            description="feature token billing",
            metadata={"policy": {"max_overdraft_credits": 2}},
        )

    assert user.credits == 1
    assert user.total_credits_spent == 0
    assert repository.created_transactions == []


@pytest.mark.asyncio
async def test_record_consumption_allows_charge_at_overdraft_floor() -> None:
    """A charge that lands exactly on the configured floor is valid."""
    user = SimpleNamespace(
        id="user-1",
        credits=1,
        total_credits_spent=0,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    tx, balance_before = await service.record_consumption(
        user_id="user-1",
        transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
        amount=3,
        description="feature token billing",
        metadata={"policy": {"max_overdraft_credits": 2}},
    )

    assert balance_before == 1
    assert user.credits == -2
    assert user.total_credits_spent == 3
    assert tx.amount == -3


@pytest.mark.asyncio
async def test_record_consumption_replays_existing_idempotent_charge() -> None:
    """A retried consume command with the same idempotency key must not charge twice."""
    user = SimpleNamespace(
        id="user-1",
        credits=7,
        total_credits_spent=3,
    )
    repository = _FakeCreditRepository(user)
    existing = SimpleNamespace(
        id="tx-existing",
        user_id="user-1",
        transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
        amount=-3,
        balance_after=7,
        tx_metadata={"idempotency_key": "feature_token_billing:exec-1"},
    )
    repository.idempotent_transactions[
        ("user-1", CreditTransactionType.WORKFLOW_CONSUME, "feature_token_billing:exec-1")
    ] = existing
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    tx, balance_before = await service.record_consumption(
        user_id="user-1",
        transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
        amount=3,
        description="feature token billing",
        metadata={
            "idempotency_key": "feature_token_billing:exec-1",
            "policy": {"max_overdraft_credits": 100},
        },
    )

    assert tx is existing
    assert balance_before == 7
    assert user.credits == 7
    assert user.total_credits_spent == 3
    assert repository.created_transactions == []
    service._finish.assert_not_awaited()
