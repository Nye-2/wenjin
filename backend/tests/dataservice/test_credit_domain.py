"""Tests for DataService credit domain behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.credit import CreditTransactionType
from src.database.models.credit_reservation import CreditReservationStatus
from src.dataservice.common.errors import CreditOverdraftLimitError
from src.dataservice.domains.credit.service import DataServiceCreditService


class _FakeCreditRepository:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user
        self.created_transactions: list[dict] = []
        self.idempotent_transactions: dict[tuple[str, CreditTransactionType, str], SimpleNamespace] = {}
        self.reservations: dict[str, SimpleNamespace] = {}
        self.idempotent_reservations: dict[str, SimpleNamespace] = {}
        self.reservation_counter = 0

    async def get_user_for_update(self, user_id: str) -> SimpleNamespace | None:
        if user_id != self.user.id:
            return None
        return self.user

    async def get_user(self, user_id: str) -> SimpleNamespace | None:
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

    async def find_reservation_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        return self.idempotent_reservations.get(idempotency_key)

    def create_credit_reservation(self, values: dict) -> SimpleNamespace:
        self.reservation_counter += 1
        values.setdefault("status", CreditReservationStatus.RESERVED)
        values.setdefault("settled_credits", 0)
        values.setdefault("transaction_id", None)
        reservation = SimpleNamespace(
            id=f"reservation-{self.reservation_counter}",
            created_at=None,
            updated_at=None,
            **values,
        )
        self.reservations[reservation.id] = reservation
        self.idempotent_reservations[reservation.idempotency_key] = reservation
        return reservation

    async def get_reservation_for_update(self, reservation_id: str) -> SimpleNamespace | None:
        return self.reservations.get(reservation_id)

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
async def test_credit_summary_exposes_reserved_and_spendable_balance() -> None:
    user = SimpleNamespace(
        id="user-1",
        credits=10,
        reserved_credits=7,
        total_credits_earned=20,
        total_credits_spent=10,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository

    summary = await service.get_credit_summary("user-1")

    assert summary == {
        "credits": 10,
        "reserved_credits": 7,
        "spendable_credits": 3,
        "total_earned": 20,
        "total_spent": 10,
    }


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
async def test_record_consumption_rejects_charge_that_spends_reserved_balance() -> None:
    user = SimpleNamespace(
        id="user-1",
        credits=10,
        reserved_credits=8,
        total_credits_spent=0,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(CreditOverdraftLimitError, match="spendable"):
        await service.record_consumption(
            user_id="user-1",
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=3,
            description="feature token billing",
            metadata={"policy": {"max_overdraft_credits": 0}},
        )

    assert user.credits == 10
    assert user.reserved_credits == 8
    assert user.total_credits_spent == 0
    assert repository.created_transactions == []


@pytest.mark.asyncio
async def test_record_consumption_rejects_reserved_balance_even_with_overdraft_policy() -> None:
    user = SimpleNamespace(
        id="user-1",
        credits=10,
        reserved_credits=8,
        total_credits_spent=0,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(CreditOverdraftLimitError, match="spendable"):
        await service.record_consumption(
            user_id="user-1",
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=3,
            description="feature token billing",
            metadata={"policy": {"max_overdraft_credits": 100}},
        )

    assert user.credits == 10
    assert user.reserved_credits == 8
    assert user.total_credits_spent == 0
    assert repository.created_transactions == []


@pytest.mark.asyncio
async def test_record_consumption_allows_charge_from_unreserved_spendable_balance() -> None:
    user = SimpleNamespace(
        id="user-1",
        credits=10,
        reserved_credits=8,
        total_credits_spent=0,
    )
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    tx, balance_before = await service.record_consumption(
        user_id="user-1",
        transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
        amount=2,
        description="feature token billing",
        metadata={"policy": {"max_overdraft_credits": 0}},
    )

    assert balance_before == 10
    assert user.credits == 8
    assert user.reserved_credits == 8
    assert user.total_credits_spent == 2
    assert tx.amount == -2


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
        tx_metadata={"idempotency_key": "mission_token_billing:exec-1"},
    )
    repository.idempotent_transactions[
        ("user-1", CreditTransactionType.WORKFLOW_CONSUME, "mission_token_billing:exec-1")
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
            "idempotency_key": "mission_token_billing:exec-1",
            "policy": {"max_overdraft_credits": 100},
        },
    )

    assert tx is existing
    assert balance_before == 7
    assert user.credits == 7
    assert user.total_credits_spent == 3
    assert repository.created_transactions == []
    service._finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_reservation_holds_spendable_balance() -> None:
    user = SimpleNamespace(id="user-1", credits=10, reserved_credits=0, total_credits_spent=0)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    reservation = await service.create_reservation(
        user_id="user-1",
        reserved_credits=4,
        idempotency_key="mission:-1",
        workspace_id="ws-1",
        mission_id="exec-1",
    )

    assert reservation.reserved_credits == 4
    assert reservation.status == CreditReservationStatus.RESERVED
    assert user.credits == 10
    assert user.reserved_credits == 4
    assert user.credits - user.reserved_credits == 6


@pytest.mark.asyncio
async def test_create_reservation_replays_by_idempotency_key() -> None:
    user = SimpleNamespace(id="user-1", credits=10, reserved_credits=0, total_credits_spent=0)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    first = await service.create_reservation(
        user_id="user-1",
        reserved_credits=4,
        idempotency_key="mission:-1",
        mission_id="exec-1",
    )
    second = await service.create_reservation(
        user_id="user-1",
        reserved_credits=4,
        idempotency_key="mission:-1",
        mission_id="exec-1",
    )

    assert second is first
    assert user.reserved_credits == 4
    assert len(repository.reservations) == 1


@pytest.mark.asyncio
async def test_create_reservation_rejects_when_spendable_balance_is_insufficient() -> None:
    user = SimpleNamespace(id="user-1", credits=5, reserved_credits=3, total_credits_spent=0)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(CreditOverdraftLimitError, match="insufficient spendable credits"):
        await service.create_reservation(
            user_id="user-1",
            reserved_credits=3,
            idempotency_key="mission:-1",
            mission_id="exec-1",
        )

    assert user.reserved_credits == 3
    assert repository.reservations == {}


@pytest.mark.asyncio
async def test_settle_reservation_creates_final_transaction_and_releases_remainder() -> None:
    user = SimpleNamespace(id="user-1", credits=20, reserved_credits=0, total_credits_spent=0)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()
    reservation = await service.create_reservation(
        user_id="user-1",
        reserved_credits=10,
        idempotency_key="mission:-1",
        workspace_id="ws-1",
        mission_id="exec-1",
        metadata={"type": "mission_reservation"},
    )

    settled, tx = await service.settle_reservation(
        reservation_id=reservation.id,
        settled_credits=6,
        description="mission settlement",
        mission_policy_id="deep_research",
        mission_id="exec-1",
        metadata={"actual_credits": 6},
    )

    assert settled.status == CreditReservationStatus.SETTLED
    assert settled.settled_credits == 6
    assert settled.transaction_id == tx.id
    assert user.reserved_credits == 0
    assert user.credits == 14
    assert user.total_credits_spent == 6
    assert tx.amount == -6
    assert tx.tx_metadata["reservation_id"] == reservation.id
    assert tx.tx_metadata["actual_credits"] == 6
    service._finish.assert_awaited_with(settled, tx)


@pytest.mark.asyncio
async def test_release_reservation_returns_all_reserved_credits() -> None:
    user = SimpleNamespace(id="user-1", credits=20, reserved_credits=0, total_credits_spent=0)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()
    reservation = await service.create_reservation(
        user_id="user-1",
        mission_id="exec-1",
        reserved_credits=7,
        idempotency_key="mission:exec-1",
    )

    released = await service.release_reservation(reservation.id, reason="platform failed")

    assert released.status == CreditReservationStatus.RELEASED
    assert user.reserved_credits == 0
    assert user.credits == 20
    assert released.metadata_json["release_reason"] == "platform failed"
