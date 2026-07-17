from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models import (
    CreditReservation,
    CreditReservationStatus,
    CreditTransaction,
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
    PricingPolicy,
    PricingPolicyKind,
    User,
)
from src.dataservice.common.errors import CreditOverdraftLimitError
from src.dataservice.domains.mission.admission import MissionAdmissionService
from src.dataservice.domains.mission.service import MissionStore
from src.dataservice.domains.model_catalog.repository import ModelCatalogRepository
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionCreatePayload,
    MissionItemDraftPayload,
    MissionLeaseClaimPayload,
    MissionReservationReconcilePayload,
    MissionResumePayload,
    MissionRunPatchPayload,
)

TABLES = [
    User.__table__,
    MissionRunRecord.__table__,
    MissionItemRecord.__table__,
    MissionReviewItemRecord.__table__,
    MissionCommitRecord.__table__,
    PricingPolicy.__table__,
    CreditReservation.__table__,
    CreditTransaction.__table__,
]


@pytest_asyncio.fixture
async def admission_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: MissionRunRecord.metadata.create_all(
                sync_connection,
                tables=TABLES,
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def model_pricing_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_model(
        _repository: ModelCatalogRepository,
        model_id: str,
    ) -> object:
        return type(
            "ModelBinding",
            (),
            {
                "model_id": model_id,
                "enabled": True,
                "pricing_policy_id": "default-model-usage",
            },
        )()

    monkeypatch.setattr(ModelCatalogRepository, "get_model", get_model)


def _mission_command() -> MissionCreatePayload:
    return MissionCreatePayload(
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
        workspace_type="sci",
        mission_policy_id="sci.research",
        title="Federated LLM research gap",
        objective="Identify a defensible research gap with evidence.",
        model_id="gpt-5.6-terra",
        reasoning_effort="xhigh",
        runtime_context_json={
            "mission_policy_snapshot": {
                "execution_budget": {
                    "max_model_calls": 100,
                    "max_tool_operations": 100,
                    "max_subagent_jobs": 20,
                    "stop_after_total_tokens": 1_000_000,
                }
            }
        },
        mission_idempotency_key="admission-1",
    )


async def _seed_user_and_policy(
    session: AsyncSession,
    *,
    credits: int,
    max_charge_credits: int,
) -> None:
    session.add(
        User(
            id="user-1",
            email="researcher@example.com",
            name="Researcher",
            hashed_password="not-used",
            credits=credits,
        )
    )
    session.add(
        PricingPolicy(
            id="pricing-1",
            policy_key="mission-sci-default",
            policy_kind=PricingPolicyKind.MISSION,
            name="SCI Mission pricing",
            config_json={
                "workspace_type": "sci",
                "estimate_max_credits": max_charge_credits,
                "max_charge_credits": max_charge_credits,
                "reservation_ttl_seconds": 3600,
            },
        )
    )
    session.add_all(
        [
            PricingPolicy(
                id="pricing-global",
                policy_key="default-global-credit",
                policy_kind=PricingPolicyKind.GLOBAL_CREDIT,
                name="Global credit anchor",
                config_json={
                    "credits_per_cny": 10,
                    "usd_to_cny": 7.3,
                    "target_margin_floor": 0.9,
                },
            ),
            PricingPolicy(
                id="pricing-model",
                policy_key="default-model-usage",
                policy_kind=PricingPolicyKind.MODEL_USAGE,
                name="Model usage",
                config_json={
                    "input_weight": 0.3,
                    "cached_input_weight": 0.05,
                    "output_weight": 1.0,
                    "reasoning_weight": 1.0,
                    "credits_per_1k_weighted_tokens": 1,
                    "min_chat_credits": 0,
                    "min_mission_model_credits": 10,
                    "cost_guard_multiplier": 1,
                    "raw_cost": {},
                    "free_tokens": 0,
                    "max_overdraft_credits": 0,
                },
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_budget_wait_resume_and_terminal_settlement_are_one_lifecycle(
    admission_session: AsyncSession,
) -> None:
    await _seed_user_and_policy(
        admission_session,
        credits=3,
        max_charge_credits=10,
    )
    admission = MissionAdmissionService(admission_session)

    created = await admission.admit(_mission_command())
    await admission_session.commit()

    assert created.created is True
    assert created.mission.status.value == "waiting"
    request_id = created.mission.snapshot_json["pending_request"]["request_id"]
    assert await admission_session.scalar(select(CreditReservation)) is None

    with pytest.raises(CreditOverdraftLimitError):
        await admission.resume(
            created.mission.mission_id,
            MissionResumePayload(request_id=request_id),
        )
    await admission_session.rollback()

    user = await admission_session.get(User, "user-1")
    assert user is not None
    user.credits = 20
    await admission_session.commit()

    resumed = await admission.resume(
        created.mission.mission_id,
        MissionResumePayload(request_id=request_id),
    )
    await admission_session.commit()

    assert resumed.mission.status.value == "planning"
    reservation = await admission_session.scalar(select(CreditReservation))
    assert reservation is not None
    assert reservation.status is CreditReservationStatus.RESERVED
    assert reservation.reserved_credits == 10
    pricing_snapshot = reservation.metadata_json["pricing_snapshot"]
    assert pricing_snapshot["mission_policy"]["id"] == "pricing-1"
    assert pricing_snapshot["model_policy"]["id"] == "pricing-model"

    model_policy = await admission_session.get(PricingPolicy, "pricing-model")
    mission_policy = await admission_session.get(PricingPolicy, "pricing-1")
    assert model_policy is not None
    assert mission_policy is not None
    model_policy.enabled = False
    model_policy.config_json = {
        **dict(model_policy.config_json),
        "min_mission_model_credits": 999,
    }
    mission_policy.config_json = {
        **dict(mission_policy.config_json),
        "base_fee_credits": 999,
    }
    await admission_session.commit()

    store = MissionStore(admission_session, autocommit=False)
    claimed = await store.claim_run_lease(
        created.mission.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=resumed.mission.state_version,
            ttl_seconds=120,
        ),
    )
    running = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="model_call_started",
                    operation_id="model-call:workspace:settlement",
                    phase="started",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": "model-call:workspace:settlement",
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                    },
                ),
                MissionItemDraftPayload(
                    item_type="usage_receipt",
                    operation_id="model-call:workspace:settlement",
                    phase="completed",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": "model-call:workspace:settlement",
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 0,
                            "output_tokens": 100,
                            "reasoning_tokens": 0,
                            "total_tokens": 200,
                        },
                    },
                ),
                MissionItemDraftPayload(
                    item_type="model_call_started",
                    operation_id="model-call:subagent:settlement",
                    phase="started",
                    producer="subagent-1",
                    payload_json={
                        "model_call_id": "model-call:subagent:settlement",
                        "model_id": "gpt-5.6-terra",
                        "parent_operation_id": "settlement-subagent-operation",
                        "job_id": "subagent-1",
                        "turn": 1,
                        "attempt": 1,
                    },
                ),
                MissionItemDraftPayload(
                    item_type="usage_receipt",
                    operation_id="model-call:subagent:settlement",
                    phase="completed",
                    producer="subagent-1",
                    payload_json={
                        "model_call_id": "model-call:subagent:settlement",
                        "model_id": "gpt-5.6-terra",
                        "parent_operation_id": "settlement-subagent-operation",
                        "job_id": "subagent-1",
                        "turn": 1,
                        "attempt": 1,
                        "usage": {
                            "input_tokens": 250,
                            "cached_input_tokens": 50,
                            "output_tokens": 50,
                            "reasoning_tokens": 20,
                            "total_tokens": 300,
                        },
                    },
                ),
            ],
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    completed = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=running.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="completed"),
        ),
    )
    await admission_session.commit()

    await admission_session.refresh(user)
    await admission_session.refresh(reservation)
    transactions = list(
        (await admission_session.scalars(select(CreditTransaction))).all()
    )
    billing_items = list(
        (
            await admission_session.scalars(
                select(MissionItemRecord).where(
                    MissionItemRecord.mission_id == created.mission.mission_id,
                    MissionItemRecord.item_type == "billing_settled",
                )
            )
        ).all()
    )

    assert completed.mission.status.value == "completed"
    assert user.credits == 10
    assert user.reserved_credits == 0
    assert reservation.status is CreditReservationStatus.SETTLED
    assert reservation.settled_credits == 10
    assert len(transactions) == 1
    assert len(billing_items) == 1
    assert billing_items[0].payload_json["usage"] == {
        "input_tokens": 350,
        "cached_input_tokens": 50,
        "output_tokens": 150,
        "reasoning_tokens": 20,
        "total_tokens": 500,
        "calculated_credits": 10,
    }


@pytest.mark.asyncio
async def test_unresolved_model_usage_retains_reservation_for_reconciliation(
    admission_session: AsyncSession,
) -> None:
    await _seed_user_and_policy(
        admission_session,
        credits=20,
        max_charge_credits=10,
    )
    created = await MissionAdmissionService(admission_session).admit(
        _mission_command()
    )
    await admission_session.commit()
    reservation = await admission_session.scalar(select(CreditReservation))
    assert reservation is not None

    store = MissionStore(admission_session, autocommit=False)
    claimed = await store.claim_run_lease(
        created.mission.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=created.mission.state_version,
            ttl_seconds=120,
        ),
    )
    model_call_id = "model-call:workspace:unresolved-settlement"
    running = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="model_call_started",
                    operation_id=model_call_id,
                    phase="started",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": model_call_id,
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                    },
                ),
                MissionItemDraftPayload(
                    item_type="model_call_terminal",
                    operation_id=model_call_id,
                    phase="failed",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": model_call_id,
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                        "outcome": "unresolved",
                        "error_type": "ProviderTransportError",
                        "detail": "Provider usage could not be confirmed",
                    },
                ),
            ],
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    failed = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=running.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="failed"),
        ),
    )
    await admission_session.commit()

    user = await admission_session.get(User, "user-1")
    await admission_session.refresh(reservation)
    transactions = list(
        (await admission_session.scalars(select(CreditTransaction))).all()
    )
    billing_items = list(
        (
            await admission_session.scalars(
                select(MissionItemRecord).where(
                    MissionItemRecord.mission_id
                    == created.mission.mission_id,
                    MissionItemRecord.item_type.in_(
                        (
                            "billing_reconciliation_required",
                            "billing_settled",
                        )
                    ),
                )
            )
        ).all()
    )

    assert user is not None
    assert failed.mission.status.value == "failed"
    assert failed.mission.snapshot_json["billing"] == {
        **created.mission.snapshot_json["billing"],
        "state": "reconciliation_required",
        "reservation_id": str(reservation.id),
        "unresolved_model_call_ids": [model_call_id],
    }
    assert reservation.status is CreditReservationStatus.RESERVED
    assert reservation.expires_at is None
    assert reservation.metadata_json["reconciliation_required"] is True
    assert reservation.metadata_json["unresolved_model_call_ids"] == [
        model_call_id
    ]
    assert user.credits == 20
    assert user.reserved_credits == 10
    assert transactions == []
    assert [item.item_type for item in billing_items] == [
        "billing_reconciliation_required"
    ]


@pytest.mark.asyncio
async def test_failed_mission_settles_exact_measured_usage(
    admission_session: AsyncSession,
) -> None:
    await _seed_user_and_policy(
        admission_session,
        credits=20,
        max_charge_credits=10,
    )
    created = await MissionAdmissionService(admission_session).admit(
        _mission_command()
    )
    await admission_session.commit()
    reservation = await admission_session.scalar(select(CreditReservation))
    assert reservation is not None

    store = MissionStore(admission_session, autocommit=False)
    claimed = await store.claim_run_lease(
        created.mission.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=created.mission.state_version,
            ttl_seconds=120,
        ),
    )
    model_call_id = "model-call:workspace:failed-measured-settlement"
    running = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="model_call_started",
                    operation_id=model_call_id,
                    phase="started",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": model_call_id,
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                    },
                ),
                MissionItemDraftPayload(
                    item_type="usage_receipt",
                    operation_id=model_call_id,
                    phase="completed",
                    producer="workspace_agent",
                    payload_json={
                        "model_call_id": model_call_id,
                        "model_id": "gpt-5.6-terra",
                        "turn": 1,
                        "attempt": 1,
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 100,
                            "total_tokens": 200,
                        },
                    },
                ),
            ],
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    failed = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=running.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="failed"),
        ),
    )
    await admission_session.commit()

    user = await admission_session.get(User, "user-1")
    await admission_session.refresh(reservation)
    assert user is not None
    assert failed.mission.status.value == "failed"
    assert failed.mission.snapshot_json["billing"]["state"] == "settled"
    assert failed.mission.snapshot_json["billing"]["settled_credits"] == 10
    assert reservation.status is CreditReservationStatus.SETTLED
    assert reservation.settled_credits == 10
    assert user.credits == 10
    assert user.reserved_credits == 0


@pytest.mark.asyncio
async def test_free_policy_admits_without_credit_reservation(
    admission_session: AsyncSession,
) -> None:
    await _seed_user_and_policy(
        admission_session,
        credits=0,
        max_charge_credits=0,
    )

    created = await MissionAdmissionService(admission_session).admit(
        _mission_command()
    )
    await admission_session.commit()

    assert created.mission.status.value == "planning"
    assert created.mission.snapshot_json["billing"]["free_policy"] is True
    assert await admission_session.scalar(select(CreditReservation)) is None


@pytest.mark.asyncio
async def test_expired_reservation_pauses_and_reactivates_same_lifecycle_record(
    admission_session: AsyncSession,
) -> None:
    await _seed_user_and_policy(
        admission_session,
        credits=20,
        max_charge_credits=10,
    )
    admission = MissionAdmissionService(admission_session)
    created = await admission.admit(_mission_command())
    await admission_session.commit()
    reservation = await admission_session.scalar(select(CreditReservation))
    assert reservation is not None
    reservation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await admission_session.commit()

    reconciled = await admission.reconcile_expired_reservations(
        MissionReservationReconcilePayload(now=datetime.now(UTC))
    )
    await admission_session.commit()

    assert reconciled.expired_mission_ids == [created.mission.mission_id]
    paused = await MissionStore(admission_session).load_run_snapshot(
        created.mission.mission_id
    )
    assert paused is not None
    assert paused.status.value == "waiting"
    assert paused.snapshot_json["waiting_reason"] == "budget"
    await admission_session.refresh(reservation)
    user = await admission_session.get(User, "user-1")
    assert user is not None
    assert reservation.status is CreditReservationStatus.EXPIRED
    assert user.reserved_credits == 0

    request_id = paused.snapshot_json["pending_request"]["request_id"]
    resumed = await admission.resume(
        created.mission.mission_id,
        MissionResumePayload(request_id=request_id),
    )
    await admission_session.commit()

    await admission_session.refresh(reservation)
    await admission_session.refresh(user)
    assert resumed.mission.status.value == "planning"
    assert resumed.mission.snapshot_json["billing"]["reservation_id"] == str(
        reservation.id
    )
    assert reservation.status is CreditReservationStatus.RESERVED
    assert user.reserved_credits == 10
