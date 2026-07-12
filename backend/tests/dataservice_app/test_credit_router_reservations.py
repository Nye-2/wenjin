"""Regression tests for credit reservation router serialization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.dataservice_app.routers import credit as credit_router
from src.dataservice_client.contracts.credit import (
    CreditReservationCreatePayload,
    CreditReservationReleasePayload,
    CreditReservationSettlePayload,
)


class _ExpiringRecord:
    _guarded_fields = {
        "id",
        "user_id",
        "workspace_id",
        "mission_id",
        "mission_item_seq",
        "scope",
        "status",
        "reserved_credits",
        "settled_credits",
        "transaction_id",
        "idempotency_key",
        "expires_at",
        "metadata_json",
        "created_at",
        "updated_at",
        "transaction_type",
        "amount",
        "balance_after",
        "description",
        "mission_policy_id",
        "operation_key",
        "task_id",
        "admin_id",
        "tx_metadata",
    }

    def __init__(self, **values: Any) -> None:
        object.__setattr__(self, "_expired", False)
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def expire(self) -> None:
        object.__setattr__(self, "_expired", True)

    def __getattribute__(self, name: str) -> Any:
        if name in object.__getattribute__(self, "_guarded_fields") and object.__getattribute__(self, "_expired"):
            raise AssertionError(f"field {name} was accessed after commit")
        return object.__getattribute__(self, name)


class _FakeUow:
    def __init__(self, *records: _ExpiringRecord) -> None:
        self.required_session = object()
        self._records = records

    async def commit(self) -> None:
        for record in self._records:
            record.expire()


def _reservation_record(**overrides: Any) -> _ExpiringRecord:
    values = {
        "id": "reservation-1",
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "mission_id": "mission-1",
        "mission_item_seq": None,
        "scope": "mission",
        "status": "reserved",
        "reserved_credits": 12,
        "settled_credits": 0,
        "transaction_id": None,
        "idempotency_key": "mission:mission-1",
        "expires_at": None,
        "metadata_json": {"kind": "mission"},
        "created_at": datetime(2026, 6, 15, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 15, tzinfo=UTC),
    }
    values.update(overrides)
    return _ExpiringRecord(**values)


@pytest.mark.asyncio
async def test_create_reservation_serializes_payload_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = _reservation_record()

    class FakeCreditService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def create_reservation(self, **_kwargs: Any):
            return reservation

    monkeypatch.setattr(credit_router, "CreditDataService", FakeCreditService)

    result = await credit_router.create_reservation(
        CreditReservationCreatePayload(
            user_id="user-1",
            scope="mission",
            reserved_credits=12,
            idempotency_key="mission:mission-1",
            workspace_id="workspace-1",
            mission_id="mission-1",
            metadata={"kind": "mission"},
        ),
        uow=_FakeUow(reservation),
    )

    assert result["status"] == "ok"
    assert result["data"]["id"] == "reservation-1"


@pytest.mark.asyncio
async def test_settle_reservation_serializes_payload_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = _reservation_record(
        status="settled",
        settled_credits=8,
        transaction_id="tx-1",
    )
    transaction = _ExpiringRecord(
        id="tx-1",
        user_id="user-1",
        transaction_type="workflow_consume",
        amount=-8,
        balance_after=42,
        description="settle",
        mission_policy_id="sci_literature_positioning",
        mission_id="mission-1",
        operation_key=None,
        workspace_id="workspace-1",
        task_id="execution-1",
        admin_id=None,
        tx_metadata={"reservation_id": "reservation-1"},
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    class FakeCreditService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def settle_reservation(self, **_kwargs: Any):
            return reservation, transaction

    monkeypatch.setattr(credit_router, "CreditDataService", FakeCreditService)

    result = await credit_router.settle_reservation(
        "reservation-1",
        CreditReservationSettlePayload(
            settled_credits=8,
            description="settle",
            mission_policy_id="sci_literature_positioning",
            mission_id="mission-1",
        ),
        uow=_FakeUow(reservation, transaction),
    )

    assert result["status"] == "ok"
    assert result["data"]["reservation"]["id"] == "reservation-1"
    assert result["data"]["transaction"]["id"] == "tx-1"


@pytest.mark.asyncio
async def test_release_reservation_serializes_payload_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = _reservation_record(status="released")

    class FakeCreditService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def release_reservation(self, *_args: Any, **_kwargs: Any):
            return reservation

    monkeypatch.setattr(credit_router, "CreditDataService", FakeCreditService)

    result = await credit_router.release_reservation(
        "reservation-1",
        CreditReservationReleasePayload(reason="not needed"),
        uow=_FakeUow(reservation),
    )

    assert result["status"] == "ok"
    assert result["data"]["id"] == "reservation-1"
    assert result["data"]["status"] == "released"
