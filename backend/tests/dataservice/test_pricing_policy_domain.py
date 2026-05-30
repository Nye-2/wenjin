"""Tests for DataService pricing policy domain."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from src.database.models.pricing_policy import PricingPolicyKind
from src.dataservice.domains.pricing.contracts import (
    CapabilityPricingPolicyConfig,
    GlobalCreditPolicyConfig,
    ModelUsagePolicyConfig,
    PricingPolicyCreateCommand,
    PricingPolicyUpdateCommand,
    PricingSimulationRequest,
    SandboxPricingPolicyConfig,
)
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


class _FakePricingPolicyRepository:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}

    async def list_policies(self, *, policy_kind: str | None = None, enabled_only: bool = False):
        rows = list(self.rows.values())
        if policy_kind is not None:
            rows = [row for row in rows if _enum_value(row.policy_kind) == policy_kind]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    async def get_policy(self, policy_id_or_key: str):
        for row in self.rows.values():
            if str(row.id) == policy_id_or_key or row.policy_key == policy_id_or_key:
                return row
        return None

    async def create_policy(self, values: dict[str, Any]):
        row = SimpleNamespace(id=f"policy-{len(self.rows) + 1}", created_at=None, updated_at=None, **values)
        self.rows[row.policy_key] = row
        return row


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _service() -> tuple[DataServicePricingPolicyService, _FakePricingPolicyRepository, _FakeSession]:
    session = _FakeSession()
    service = DataServicePricingPolicyService(session, autocommit=True)  # type: ignore[arg-type]
    repository = _FakePricingPolicyRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def test_global_credit_policy_accepts_positive_exchange_rate() -> None:
    policy = GlobalCreditPolicyConfig(credits_per_cny=10)

    assert policy.credits_per_cny == 10


def test_model_usage_policy_calculates_weighted_tokens() -> None:
    service = DataServicePricingPolicyService(None, autocommit=False)  # type: ignore[arg-type]
    policy = ModelUsagePolicyConfig(tokens_per_credit=1000, prompt_token_weight=1, completion_token_weight=4)

    result = service.simulate(
        PricingSimulationRequest(
            policy_kind="model_usage",
            global_policy=GlobalCreditPolicyConfig(credits_per_cny=10),
            model_usage_policy=policy,
            prompt_tokens=1000,
            completion_tokens=500,
        )
    )

    assert result.charge_credits == 3
    assert result.breakdown["weighted_tokens"] == 3000


def test_raw_cost_guard_can_dominate_weighted_token_price() -> None:
    service = DataServicePricingPolicyService(None, autocommit=False)  # type: ignore[arg-type]
    policy = ModelUsagePolicyConfig(
        tokens_per_credit=1000000,
        prompt_token_weight=1,
        completion_token_weight=1,
        input_cny_per_1k_tokens=1.0,
        output_cny_per_1k_tokens=9.0,
        raw_cost_markup=2.0,
    )

    result = service.simulate(
        PricingSimulationRequest(
            policy_kind="model_usage",
            global_policy=GlobalCreditPolicyConfig(credits_per_cny=10),
            model_usage_policy=policy,
            prompt_tokens=1000,
            completion_tokens=1000,
        )
    )

    assert result.raw_cost_cny == 10
    assert result.charge_credits == 200
    assert result.breakdown["raw_cost_guard_credits"] == 200


def test_invalid_negative_rates_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GlobalCreditPolicyConfig(credits_per_cny=-1)
    with pytest.raises(ValidationError):
        ModelUsagePolicyConfig(tokens_per_credit=-100)


def test_capability_policy_requires_max_charge_not_below_estimate() -> None:
    with pytest.raises(ValidationError):
        CapabilityPricingPolicyConfig(estimate_max_credits=20, max_charge_credits=10)


def test_sandbox_policy_requires_at_least_one_tier() -> None:
    with pytest.raises(ValidationError):
        SandboxPricingPolicyConfig(tiers={})


@pytest.mark.asyncio
async def test_create_pricing_policy_validates_config_and_returns_record() -> None:
    service, repository, session = _service()

    record = await service.create_policy(
        PricingPolicyCreateCommand(
            policy_key="model-standard",
            policy_kind=PricingPolicyKind.MODEL_USAGE,
            name="Standard model usage",
            config={
                "tokens_per_credit": 1000,
                "prompt_token_weight": 1,
                "completion_token_weight": 4,
            },
        ),
        admin_id="admin-1",
    )

    assert record.policy_key == "model-standard"
    assert record.policy_kind == "model_usage"
    assert record.config["tokens_per_credit"] == 1000
    assert repository.rows["model-standard"].created_by_admin_id == "admin-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_update_pricing_policy_increments_version_and_revalidates_config() -> None:
    service, repository, _session = _service()
    await service.create_policy(
        PricingPolicyCreateCommand(
            policy_key="global",
            policy_kind="global_credit",
            name="Global",
            config={"credits_per_cny": 10},
        ),
        admin_id="admin-1",
    )

    record = await service.update_policy(
        "global",
        PricingPolicyUpdateCommand(config={"credits_per_cny": 12}, name="Global v2"),
        admin_id="admin-2",
    )

    assert record is not None
    assert record.version == 2
    assert record.name == "Global v2"
    assert record.config["credits_per_cny"] == 12
    assert repository.rows["global"].updated_by_admin_id == "admin-2"


@pytest.mark.asyncio
async def test_list_pricing_policies_filters_enabled_and_kind() -> None:
    service, _repository, _session = _service()
    await service.create_policy(
        PricingPolicyCreateCommand(policy_key="global", policy_kind="global_credit", name="Global", config={"credits_per_cny": 10})
    )
    await service.create_policy(
        PricingPolicyCreateCommand(policy_key="model", policy_kind="model_usage", name="Model", config={"tokens_per_credit": 1000})
    )
    await service.disable_policy("model", admin_id="admin-1")

    records = await service.list_policies(policy_kind="model_usage", enabled_only=True)

    assert records == []


@pytest.mark.asyncio
async def test_disable_pricing_policy_marks_disabled_and_increments_version() -> None:
    service, _repository, _session = _service()
    await service.create_policy(
        PricingPolicyCreateCommand(policy_key="global", policy_kind="global_credit", name="Global", config={"credits_per_cny": 10})
    )

    record = await service.disable_policy("global", admin_id="admin-1")

    assert record is not None
    assert record.enabled is False
    assert record.version == 2
