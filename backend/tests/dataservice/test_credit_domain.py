"""Tests for DataService-owned balance projections and Mission reservations."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.credit_reservation import CreditReservationStatus
from src.dataservice.common.errors import (
    CreditOverdraftLimitError,
    DataServiceValidationError,
)
from src.dataservice.domains.credit.service import (
    DataServiceCreditService,
    _decode_periodic_cursor,
    _encode_periodic_cursor,
)


class _FakeCreditRepository:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user
        self.created_transactions: list[dict] = []
        self.reservations: dict[str, SimpleNamespace] = {}
        self.idempotent_reservations: dict[str, SimpleNamespace] = {}
        self.reservation_counter = 0

    async def get_user_for_update(self, user_id: str) -> SimpleNamespace | None:
        return self.user if user_id == self.user.id else None

    async def get_user(self, user_id: str) -> SimpleNamespace | None:
        return self.user if user_id == self.user.id else None

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

    async def get_reservation_for_update(
        self,
        reservation_id: str,
    ) -> SimpleNamespace | None:
        return self.reservations.get(reservation_id)

    async def get_credit_transaction(self, transaction_id: str):  # noqa: ANN201
        return next(
            (
                item
                for item in self.created_transactions
                if item.get("id") == transaction_id
            ),
            None,
        )

    async def find_credit_transaction_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type,  # noqa: ANN001
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        return next(
            (
                SimpleNamespace(**item)
                for item in self.created_transactions
                if item["user_id"] == user_id
                and item["transaction_type"] == transaction_type
                and item.get("idempotency_key") == idempotency_key
            ),
            None,
        )

    def create_credit_transaction(self, values: dict) -> SimpleNamespace:
        transaction = SimpleNamespace(
            id=f"tx-{len(self.created_transactions) + 1}",
            **values,
        )
        self.created_transactions.append(vars(transaction))
        return transaction


def _user(*, credits: int, reserved_credits: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id="user-1",
        credits=credits,
        reserved_credits=reserved_credits,
        thread_consumed_tokens=12_345,
        reserved_thread_free_tokens=6_789,
        total_credits_earned=20,
        total_credits_spent=10,
    )


@pytest.mark.asyncio
async def test_credit_summary_exposes_constant_time_usage_projections() -> None:
    repository = _FakeCreditRepository(_user(credits=10, reserved_credits=7))
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository

    summary = await service.get_credit_summary("user-1")

    assert summary == {
        "credits": 10,
        "reserved_credits": 7,
        "spendable_credits": 3,
        "thread_consumed_tokens": 12_345,
        "reserved_thread_free_tokens": 6_789,
        "total_earned": 20,
        "total_spent": 10,
    }


@pytest.mark.asyncio
async def test_admin_deduction_cannot_consume_an_active_hold() -> None:
    user = _user(credits=10, reserved_credits=4)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(
        CreditOverdraftLimitError,
        match="cannot consume credits held by active work",
    ):
        await service.admin_adjust(
            admin_id="admin-1",
            target_user_id="user-1",
            amount=-7,
            transaction_type="admin_deduct",
            description="deduct",
        )

    assert user.credits == 10
    assert repository.created_transactions == []


@pytest.mark.asyncio
async def test_registration_bonus_rule_is_idempotent_per_user() -> None:
    user = _user(credits=10)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()
    rule = SimpleNamespace(id="rule-registration", amount=5)

    first = await service.apply_registration_bonus_from_rule(
        user_id=user.id,
        rule=rule,
    )
    replay = await service.apply_registration_bonus_from_rule(
        user_id=user.id,
        rule=rule,
    )

    assert replay.id == first.id
    assert user.credits == 15
    assert user.total_credits_earned == 25
    assert len(repository.created_transactions) == 1
    assert first.idempotency_key == "registration-bonus:rule-registration"


def _periodic_rule(
    rule_id: str,
    *,
    amount: int,
    now: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=rule_id,
        enabled=True,
        rule_type="periodic",
        amount=amount,
        config={"cron": "0 * * * *", "target_filter": {}},
        last_triggered_at=now - timedelta(hours=1),
        created_at=now - timedelta(days=1),
    )


def _periodic_user(user_id: str, *, now: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        **{
            **vars(_user(credits=10)),
            "id": user_id,
            "created_at": now - timedelta(days=1),
            "last_login": now - timedelta(minutes=1),
            "is_superuser": False,
        }
    )


class _PeriodicRepository:
    def __init__(
        self,
        *,
        rules: list[SimpleNamespace],
        users: list[SimpleNamespace],
    ) -> None:
        self.rules = {rule.id: rule for rule in rules}
        self.users = {user.id: user for user in users}
        self.created: list[dict] = []
        self.ledger: dict[tuple[str, str, str], SimpleNamespace] = {}
        self.locked_users: list[str] = []
        self.user_page_queries: list[dict] = []

    async def get_next_enabled_grant_rule_for_update(
        self,
        rule_type,  # noqa: ANN001
        *,
        after_rule_id: str | None,
        created_through: datetime,
    ) -> SimpleNamespace | None:
        for rule_id in sorted(self.rules):
            rule = self.rules[rule_id]
            if (
                (after_rule_id is None or rule_id > after_rule_id)
                and rule.enabled
                and rule.rule_type == rule_type
                and rule.created_at <= created_through
            ):
                return rule
        return None

    async def get_grant_rule_for_update(
        self,
        rule_id: str,
    ) -> SimpleNamespace | None:
        return self.rules.get(rule_id)

    async def list_user_ids_for_periodic_credit_filter(
        self,
        *,
        active_since: datetime | None,
        role: str | None,
        created_through: datetime,
        after_user_id: str | None,
        limit: int,
    ) -> list[str]:
        self.user_page_queries.append(
            {
                "after_user_id": after_user_id,
                "created_through": created_through,
                "limit": limit,
            }
        )
        user_ids = []
        for user_id in sorted(self.users):
            user = self.users[user_id]
            if after_user_id is not None and user_id <= after_user_id:
                continue
            if user.created_at > created_through:
                continue
            if active_since is not None and user.last_login < active_since:
                continue
            if role == "user" and user.is_superuser:
                continue
            if role == "admin" and not user.is_superuser:
                continue
            user_ids.append(user_id)
        return user_ids[:limit]

    async def get_user_for_update(
        self,
        user_id: str,
    ) -> SimpleNamespace | None:
        self.locked_users.append(user_id)
        return self.users.get(user_id)

    async def find_credit_transaction_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type,  # noqa: ANN001
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        transaction_type_value = getattr(
            transaction_type,
            "value",
            transaction_type,
        )
        return self.ledger.get(
            (user_id, str(transaction_type_value), idempotency_key)
        )

    def create_credit_transaction(self, values: dict) -> SimpleNamespace:
        transaction = SimpleNamespace(
            id=f"tx-{len(self.created) + 1}",
            **values,
        )
        transaction_type_value = getattr(
            transaction.transaction_type,
            "value",
            transaction.transaction_type,
        )
        key = (
            str(transaction.user_id),
            str(transaction_type_value),
            str(transaction.idempotency_key),
        )
        assert key not in self.ledger
        self.ledger[key] = transaction
        self.created.append(values)
        return transaction


class _ConcurrentPeriodicRepository(_PeriodicRepository):
    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self._user_page_arrivals = 0
        self._user_page_barrier = asyncio.Event()
        self._user_locks = {
            user_id: asyncio.Lock() for user_id in self.users
        }
        self._held_locks: dict[tuple[asyncio.Task, str], asyncio.Lock] = {}

    async def list_user_ids_for_periodic_credit_filter(
        self,
        *,
        active_since: datetime | None,
        role: str | None,
        created_through: datetime,
        after_user_id: str | None,
        limit: int,
    ) -> list[str]:
        user_ids = await super().list_user_ids_for_periodic_credit_filter(
            active_since=active_since,
            role=role,
            created_through=created_through,
            after_user_id=after_user_id,
            limit=limit,
        )
        if after_user_id is None:
            self._user_page_arrivals += 1
            if self._user_page_arrivals == 2:
                self._user_page_barrier.set()
            await self._user_page_barrier.wait()
        return user_ids

    async def get_user_for_update(
        self,
        user_id: str,
    ) -> SimpleNamespace | None:
        task = asyncio.current_task()
        assert task is not None
        lock = self._user_locks[user_id]
        await lock.acquire()
        self._held_locks[(task, user_id)] = lock
        return await super().get_user_for_update(user_id)

    async def find_credit_transaction_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type,  # noqa: ANN001
        idempotency_key: str,
    ) -> SimpleNamespace | None:
        transaction = await super().find_credit_transaction_by_idempotency_key(
            user_id=user_id,
            transaction_type=transaction_type,
            idempotency_key=idempotency_key,
        )
        if transaction is not None:
            self._release_user_lock(user_id)
        return transaction

    def create_credit_transaction(self, values: dict) -> SimpleNamespace:
        transaction = super().create_credit_transaction(values)
        self._release_user_lock(str(transaction.user_id))
        return transaction

    def _release_user_lock(self, user_id: str) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._held_locks.pop((task, user_id)).release()


def _periodic_service(repository: _PeriodicRepository) -> DataServiceCreditService:
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository  # type: ignore[assignment]
    service._finish = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_periodic_grant_cursor_retries_each_user_page_idempotently() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    repository = _PeriodicRepository(
        rules=[_periodic_rule("rule-1", amount=3, now=now)],
        users=[
            _periodic_user(f"user-{index:03d}", now=now)
            for index in range(1, 6)
        ],
    )
    service = _periodic_service(repository)

    first = await service.process_periodic_grant_page(now=now, batch_size=2)
    second = await service.process_periodic_grant_page(
        cursor=first["next_cursor"],
        batch_size=2,
    )
    retried_second = await service.process_periodic_grant_page(
        cursor=first["next_cursor"],
        batch_size=2,
    )
    third = await service.process_periodic_grant_page(
        cursor=retried_second["next_cursor"],
        batch_size=2,
    )

    assert [first["users_granted"], second["users_granted"]] == [2, 2]
    assert retried_second["users_granted"] == 0
    assert retried_second["next_cursor"] == second["next_cursor"]
    assert third["users_granted"] == 1
    assert len(repository.created) == 5
    assert all(user.credits == 13 for user in repository.users.values())
    assert repository.rules["rule-1"].last_triggered_at == now
    assert [query["after_user_id"] for query in repository.user_page_queries] == [
        None,
        "user-002",
        "user-002",
        "user-004",
    ]
    assert all(query["limit"] == 3 for query in repository.user_page_queries)


@pytest.mark.asyncio
async def test_periodic_grant_restart_replays_committed_pages_then_recovers() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    repository = _PeriodicRepository(
        rules=[_periodic_rule("rule-1", amount=3, now=now)],
        users=[
            _periodic_user(f"user-{index:03d}", now=now)
            for index in range(1, 6)
        ],
    )
    service = _periodic_service(repository)

    committed_page = await service.process_periodic_grant_page(
        now=now,
        batch_size=2,
    )
    restarted_page = await service.process_periodic_grant_page(
        now=now + timedelta(minutes=2),
        batch_size=2,
    )
    cursor = restarted_page["next_cursor"]
    recovered_grants = restarted_page["users_granted"]
    while cursor is not None:
        page = await service.process_periodic_grant_page(
            cursor=cursor,
            batch_size=2,
        )
        recovered_grants += page["users_granted"]
        cursor = page["next_cursor"]

    assert committed_page["users_granted"] == 2
    assert restarted_page["users_granted"] == 0
    assert recovered_grants == 3
    assert len(repository.created) == 5
    assert all(user.credits == 13 for user in repository.users.values())


@pytest.mark.asyncio
async def test_periodic_grant_scan_handles_multiple_rules_across_batches() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    repository = _PeriodicRepository(
        rules=[
            _periodic_rule("rule-a", amount=2, now=now),
            _periodic_rule("rule-b", amount=5, now=now),
        ],
        users=[
            _periodic_user(f"user-{index:03d}", now=now)
            for index in range(1, 4)
        ],
    )
    service = _periodic_service(repository)
    summary = {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    cursor = None
    first_page = True

    while first_page or cursor is not None:
        page = await service.process_periodic_grant_page(
            now=now if first_page else None,
            cursor=cursor,
            batch_size=2,
        )
        if first_page:
            late_rule = _periodic_rule("rule-z", amount=11, now=now)
            late_rule.created_at = now + timedelta(seconds=1)
            repository.rules[late_rule.id] = late_rule
        first_page = False
        for key in summary:
            summary[key] += page[key]
        cursor = page["next_cursor"]

    assert summary == {
        "rules_evaluated": 2,
        "rules_fired": 2,
        "users_granted": 6,
    }
    assert len(repository.created) == 6
    assert all(user.credits == 17 for user in repository.users.values())
    assert all(query["limit"] == 3 for query in repository.user_page_queries)


@pytest.mark.asyncio
async def test_concurrent_periodic_pages_share_user_lock_and_ledger_idempotency() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    repository = _ConcurrentPeriodicRepository(
        rules=[_periodic_rule("rule-1", amount=3, now=now)],
        users=[_periodic_user("user-001", now=now)],
    )
    first_service = _periodic_service(repository)
    second_service = _periodic_service(repository)

    pages = await asyncio.gather(
        first_service.process_periodic_grant_page(now=now, batch_size=1),
        second_service.process_periodic_grant_page(now=now, batch_size=1),
    )

    assert sorted(page["users_granted"] for page in pages) == [0, 1]
    assert repository.users["user-001"].credits == 13
    assert len(repository.created) == 1
    assert repository.locked_users == ["user-001", "user-001"]


@pytest.mark.asyncio
async def test_periodic_grant_rejects_an_invalid_cursor_before_querying() -> None:
    repository = _PeriodicRepository(rules=[], users=[])
    service = _periodic_service(repository)

    with pytest.raises(
        DataServiceValidationError,
        match="Invalid periodic credit grant cursor",
    ):
        await service.process_periodic_grant_page(cursor="not-a-cursor")

    assert repository.user_page_queries == []


@pytest.mark.asyncio
async def test_periodic_grant_cursor_cannot_override_canonical_rule_amount() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    repository = _PeriodicRepository(
        rules=[_periodic_rule("rule-1", amount=3, now=now)],
        users=[
            _periodic_user("user-001", now=now),
            _periodic_user("user-002", now=now),
        ],
    )
    service = _periodic_service(repository)
    first = await service.process_periodic_grant_page(now=now, batch_size=1)
    state = _decode_periodic_cursor(first["next_cursor"])
    tampered = _encode_periodic_cursor(replace(state, amount=300))

    page = await service.process_periodic_grant_page(
        cursor=tampered,
        batch_size=1,
    )

    assert page["users_granted"] == 0
    assert repository.users["user-001"].credits == 13
    assert repository.users["user-002"].credits == 10
    assert len(repository.created) == 1


@pytest.mark.asyncio
async def test_periodic_grant_stops_when_rule_changes_between_pages() -> None:
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    rule = _periodic_rule("rule-1", amount=3, now=now)
    repository = _PeriodicRepository(
        rules=[rule],
        users=[
            _periodic_user("user-001", now=now),
            _periodic_user("user-002", now=now),
        ],
    )
    service = _periodic_service(repository)
    first = await service.process_periodic_grant_page(now=now, batch_size=1)
    rule.amount = 30

    page = await service.process_periodic_grant_page(
        cursor=first["next_cursor"],
        batch_size=1,
    )

    assert page["users_granted"] == 0
    assert repository.users["user-002"].credits == 10


@pytest.mark.asyncio
async def test_create_reservation_holds_spendable_balance_and_replays() -> None:
    user = _user(credits=10)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    first = await service.create_reservation(
        user_id="user-1",
        reserved_credits=4,
        idempotency_key="mission:exec-1",
        workspace_id="ws-1",
        mission_id="exec-1",
    )
    second = await service.create_reservation(
        user_id="user-1",
        reserved_credits=4,
        idempotency_key="mission:exec-1",
        workspace_id="ws-1",
        mission_id="exec-1",
    )

    assert second is first
    assert user.reserved_credits == 4
    assert user.credits - user.reserved_credits == 6
    assert len(repository.reservations) == 1


@pytest.mark.asyncio
async def test_create_reservation_rejects_insufficient_spendable_balance() -> None:
    user = _user(credits=5, reserved_credits=3)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()

    with pytest.raises(
        CreditOverdraftLimitError,
        match="insufficient spendable credits",
    ):
        await service.create_reservation(
            user_id="user-1",
            reserved_credits=3,
            idempotency_key="mission:exec-1",
            mission_id="exec-1",
        )

    assert user.reserved_credits == 3
    assert repository.reservations == {}


@pytest.mark.asyncio
async def test_settle_reservation_is_idempotent_and_releases_remainder() -> None:
    user = _user(credits=20)
    repository = _FakeCreditRepository(user)
    service = DataServiceCreditService(MagicMock(), autocommit=False)
    service.repository = repository
    service._finish = AsyncMock()
    reservation = await service.create_reservation(
        user_id="user-1",
        reserved_credits=10,
        idempotency_key="mission:exec-1",
        workspace_id="ws-1",
        mission_id="exec-1",
    )

    settled, transaction = await service.settle_reservation(
        reservation_id=reservation.id,
        settled_credits=6,
        description="mission settlement",
        mission_policy_id="sci.research",
        mission_id="exec-1",
        metadata={"actual_credits": 6},
    )

    assert settled.status == CreditReservationStatus.SETTLED
    assert user.reserved_credits == 0
    assert user.credits == 14
    assert user.total_credits_spent == 16
    assert transaction.amount == -6
    assert transaction.idempotency_key == (
        f"reservation-settlement:{reservation.id}"
    )

    replayed, replayed_transaction = await service.settle_reservation(
        reservation_id=reservation.id,
        settled_credits=9,
        description="ignored retry",
    )
    assert replayed is settled
    assert replayed_transaction is not None
    assert user.credits == 14


@pytest.mark.asyncio
async def test_release_reservation_returns_the_full_hold() -> None:
    user = _user(credits=20)
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

    released = await service.release_reservation(
        reservation.id,
        reason="platform failed",
    )

    assert released.status == CreditReservationStatus.RELEASED
    assert user.reserved_credits == 0
    assert user.credits == 20
    assert released.metadata_json["release_reason"] == "platform failed"
