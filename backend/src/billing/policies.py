"""Pure credit pricing calculations shared across process boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenBillingPolicy:
    """Token-to-credit billing parameters for one usage surface."""

    enabled: bool
    free_tokens: int
    tokens_per_credit: int
    max_overdraft_credits: int

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "enabled": self.enabled,
            "free_tokens": self.free_tokens,
            "tokens_per_credit": self.tokens_per_credit,
            "max_overdraft_credits": self.max_overdraft_credits,
        }


@dataclass(frozen=True, slots=True)
class TokenBillingCharge:
    """Calculated billing delta for one token usage event."""

    free_tokens_applied: int
    billable_tokens: int
    credits_to_charge: int
    historical_tokens_after: int


@dataclass(frozen=True, slots=True)
class GlobalCreditPolicy:
    """Global credit anchor for internal pricing calculations."""

    credits_per_cny: float = 10.0
    usd_to_cny: float = 7.3
    target_margin_floor: float = 0.9
    show_token_details_to_users: bool = False

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "credits_per_cny": self.credits_per_cny,
            "usd_to_cny": self.usd_to_cny,
            "target_margin_floor": self.target_margin_floor,
            "show_token_details_to_users": self.show_token_details_to_users,
        }


@dataclass(frozen=True, slots=True)
class ModelUsageCreditCharge:
    """Calculated policy-driven model usage charge."""

    billable_tokens: int
    weighted_tokens: float
    weighted_credits: int
    raw_cost_usd: float
    raw_cost_cny: float
    raw_cost_credits: float
    raw_cost_guard_credits: int
    minimum_credits: int
    credits_to_charge: int

    def breakdown(self) -> dict[str, int | float]:
        return {
            "billable_tokens": self.billable_tokens,
            "weighted_tokens": self.weighted_tokens,
            "weighted_credits": self.weighted_credits,
            "raw_cost_usd": self.raw_cost_usd,
            "raw_cost_cny": self.raw_cost_cny,
            "raw_cost_credits": self.raw_cost_credits,
            "raw_cost_guard_credits": self.raw_cost_guard_credits,
            "minimum_credits": self.minimum_credits,
        }


@dataclass(frozen=True, slots=True)
class MissionPricingEstimate:
    """Value-based Mission estimate used before long-running work."""

    base_fee_credits: int
    estimate_min_credits: int
    estimate_max_credits: int
    max_charge_credits: int

    def as_dict(self) -> dict[str, int]:
        return {
            "base_fee_credits": self.base_fee_credits,
            "estimate_min_credits": self.estimate_min_credits,
            "estimate_max_credits": self.estimate_max_credits,
            "max_charge_credits": self.max_charge_credits,
        }


@dataclass(frozen=True, slots=True)
class SandboxPricingEstimate:
    """Estimated sandbox operation charge."""

    operation: str
    tier: str
    duration_seconds: int
    billable_seconds: int
    startup_fee_credits: int
    runtime_credits: int
    credits: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "operation": self.operation,
            "tier": self.tier,
            "duration_seconds": self.duration_seconds,
            "billable_seconds": self.billable_seconds,
            "startup_fee_credits": self.startup_fee_credits,
            "runtime_credits": self.runtime_credits,
            "credits": self.credits,
        }


@dataclass(frozen=True, slots=True)
class OperationBillingPolicy:
    """Fixed credit billing parameters for non-LLM operations."""

    enabled: bool
    run_python_credits: int
    max_overdraft_credits: int

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "enabled": self.enabled,
            "run_python_credits": self.run_python_credits,
            "max_overdraft_credits": self.max_overdraft_credits,
        }


def calculate_token_billing_charge(
    *,
    policy: TokenBillingPolicy,
    total_tokens: int,
    historical_tokens_before: int,
) -> TokenBillingCharge:
    """Calculate token billing deltas under a cumulative free-token policy."""
    normalized_total = max(int(total_tokens or 0), 0)
    historical_before = max(int(historical_tokens_before or 0), 0)
    historical_after = historical_before + normalized_total

    if not policy.enabled or normalized_total <= 0:
        return TokenBillingCharge(
            free_tokens_applied=0,
            billable_tokens=0,
            credits_to_charge=0,
            historical_tokens_after=historical_after,
        )

    overage_before = max(historical_before - policy.free_tokens, 0)
    overage_after = max(historical_after - policy.free_tokens, 0)
    billable_tokens = max(overage_after - overage_before, 0)
    free_tokens_applied = max(normalized_total - billable_tokens, 0)
    credits_to_charge = (
        math.ceil(billable_tokens / policy.tokens_per_credit)
        if billable_tokens > 0
        else 0
    )
    return TokenBillingCharge(
        free_tokens_applied=free_tokens_applied,
        billable_tokens=billable_tokens,
        credits_to_charge=credits_to_charge,
        historical_tokens_after=historical_after,
    )


def calculate_weighted_tokens(
    model_policy: Any,
    token_usage: dict[str, Any],
) -> float:
    """Calculate weighted model tokens under the current value-pricing schema."""
    policy = _policy_config(model_policy)
    usage = _normalize_usage_dict(token_usage)
    input_weight = _float_policy_value(policy, "input_weight", default=0.3)
    cached_input_weight = _float_policy_value(policy, "cached_input_weight", default=0.05)
    output_weight = _float_policy_value(policy, "output_weight", default=1.0)
    reasoning_weight = _float_policy_value(policy, "reasoning_weight", default=1.0)

    return (
        usage["input_tokens"] * input_weight
        + usage["cached_input_tokens"] * cached_input_weight
        + usage["output_tokens"] * output_weight
        + usage["reasoning_tokens"] * reasoning_weight
    )


def calculate_model_usage_credits(
    *,
    model_policy: Any,
    global_policy: Any | None = None,
    token_usage: dict[str, Any],
    surface: str,
    billable_tokens: int | None = None,
) -> ModelUsageCreditCharge:
    """Calculate model usage credits from admin pricing policy config."""
    policy = _policy_config(model_policy)
    global_credit_policy = _coerce_global_credit_policy(global_policy)
    usage = _normalize_usage_dict(token_usage)
    billable_usage = _billable_usage_slice(usage, billable_tokens)
    normalized_billable_tokens = billable_usage["total_tokens"]

    if normalized_billable_tokens <= 0 or not _bool_policy_value(policy, "enabled", default=True):
        return ModelUsageCreditCharge(
            billable_tokens=normalized_billable_tokens,
            weighted_tokens=0,
            weighted_credits=0,
            raw_cost_usd=0,
            raw_cost_cny=0,
            raw_cost_credits=0,
            raw_cost_guard_credits=0,
            minimum_credits=0,
            credits_to_charge=0,
        )

    weighted_tokens = calculate_weighted_tokens(policy, billable_usage)
    credits_per_1k = _float_policy_value(
        policy,
        "credits_per_1k_weighted_tokens",
        default=6.0,
    )
    weighted_credits = math.ceil(weighted_tokens / 1000 * credits_per_1k)
    raw_cost_usd = _raw_cost_usd(policy, billable_usage)
    raw_cost_cny = raw_cost_usd * global_credit_policy.usd_to_cny
    raw_cost_credits = raw_cost_cny * global_credit_policy.credits_per_cny
    multiplier = _float_policy_value(policy, "cost_guard_multiplier", default=20.0)
    minimum_credits = _surface_minimum(policy, surface)

    raw_cost_guard_credits = math.ceil(raw_cost_credits * multiplier)
    credits_to_charge = max(minimum_credits, weighted_credits, raw_cost_guard_credits)
    return ModelUsageCreditCharge(
        billable_tokens=normalized_billable_tokens,
        weighted_tokens=round(weighted_tokens, 6),
        weighted_credits=weighted_credits,
        raw_cost_usd=round(raw_cost_usd, 12),
        raw_cost_cny=round(raw_cost_cny, 12),
        raw_cost_credits=round(raw_cost_credits, 12),
        raw_cost_guard_credits=raw_cost_guard_credits,
        minimum_credits=minimum_credits,
        credits_to_charge=credits_to_charge,
    )


def calculate_mission_estimate(mission_policy: Any) -> MissionPricingEstimate:
    """Calculate value-based Mission reservation bounds."""
    policy = _policy_config(mission_policy)
    base_fee = _int_policy_value(policy, "base_fee_credits", default=0)
    estimate_min = max(_int_policy_value(policy, "estimate_min_credits", default=base_fee), base_fee)
    estimate_max = max(_int_policy_value(policy, "estimate_max_credits", default=estimate_min), estimate_min)
    max_charge = max(_int_policy_value(policy, "max_charge_credits", default=estimate_max), estimate_max)
    return MissionPricingEstimate(
        base_fee_credits=base_fee,
        estimate_min_credits=estimate_min,
        estimate_max_credits=estimate_max,
        max_charge_credits=max_charge,
    )


def calculate_sandbox_estimate(
    sandbox_policy: Any,
    *,
    operation: str,
    duration_seconds: int,
    tier: str | None = None,
) -> SandboxPricingEstimate:
    """Estimate sandbox credits from startup fee, tier, and rounded runtime."""
    policy = _policy_config(sandbox_policy)
    normalized_operation = str(operation or "").strip()
    configured_operation = str(policy.get("operation") or normalized_operation).strip()
    if configured_operation and normalized_operation and configured_operation != normalized_operation:
        raise ValueError(f"Unsupported sandbox operation: {operation}")

    tier_name = str(tier or policy.get("default_tier") or "").strip()
    tier_config = _resolve_tier_config(policy.get("tiers"), tier_name)
    if not tier_name:
        tier_name = str(tier_config.get("tier") or "default")
    credits_per_minute = _coerce_int(tier_config.get("credits_per_minute"), default=0)
    minimum_billable_seconds = _int_policy_value(policy, "minimum_billable_seconds", default=0)
    normalized_duration = max(int(duration_seconds or 0), 0)
    billable_seconds = max(normalized_duration, minimum_billable_seconds)
    if billable_seconds > 0:
        billable_seconds = math.ceil(billable_seconds / 60) * 60
    startup_fee = _int_policy_value(policy, "startup_fee_credits", default=0)
    runtime_credits = math.ceil(billable_seconds / 60) * credits_per_minute
    credits = startup_fee + runtime_credits
    max_charge = _int_policy_value(policy, "max_charge_credits", default=0)
    if max_charge > 0:
        credits = min(credits, max_charge)
    return SandboxPricingEstimate(
        operation=normalized_operation,
        tier=tier_name,
        duration_seconds=normalized_duration,
        billable_seconds=billable_seconds,
        startup_fee_credits=startup_fee,
        runtime_credits=runtime_credits,
        credits=credits,
    )


def _policy_config(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        config = raw.get("config")
        if isinstance(config, dict):
            merged = dict(config)
            for key in ("enabled", "policy_key", "policy_kind", "id", "version"):
                if key in raw:
                    merged[key] = raw[key]
            return merged
        return dict(raw)
    config = getattr(raw, "config", None)
    if isinstance(config, dict):
        merged = dict(config)
        for key in ("enabled", "policy_key", "policy_kind", "id", "version"):
            if hasattr(raw, key):
                merged[key] = getattr(raw, key)
        return merged
    config_json = getattr(raw, "config_json", None)
    if isinstance(config_json, dict):
        return dict(config_json)
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {}


def _coerce_global_credit_policy(raw: Any | None) -> GlobalCreditPolicy:
    policy = _policy_config(raw)
    return GlobalCreditPolicy(
        credits_per_cny=_float_policy_value(policy, "credits_per_cny", default=10.0),
        usd_to_cny=_float_policy_value(policy, "usd_to_cny", default=7.3),
        target_margin_floor=_float_policy_value(policy, "target_margin_floor", default=0.9),
        show_token_details_to_users=_bool_policy_value(
            policy,
            "show_token_details_to_users",
            default=False,
        ),
    )


def _normalize_usage_dict(token_usage: dict[str, Any]) -> dict[str, int]:
    input_tokens = _coerce_int(
        token_usage.get("input_tokens", token_usage.get("prompt_tokens", 0)),
        default=0,
    )
    output_tokens = _coerce_int(
        token_usage.get("output_tokens", token_usage.get("completion_tokens", 0)),
        default=0,
    )
    cached_input_tokens = _coerce_int(
        token_usage.get(
            "cached_input_tokens",
            token_usage.get("cache_read_input_tokens", token_usage.get("cached_tokens", 0)),
        ),
        default=0,
    )
    reasoning_tokens = _coerce_int(token_usage.get("reasoning_tokens", 0), default=0)
    total_tokens = _coerce_int(token_usage.get("total_tokens", 0), default=0)
    if total_tokens <= 0:
        total_tokens = input_tokens + cached_input_tokens + output_tokens + reasoning_tokens
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }


def _billable_usage_slice(usage: dict[str, int], billable_tokens: int | None) -> dict[str, int]:
    if billable_tokens is None:
        return dict(usage)
    normalized_billable = max(int(billable_tokens or 0), 0)
    total_tokens = max(int(usage.get("total_tokens", 0) or 0), 0)
    if total_tokens <= 0 or normalized_billable >= total_tokens:
        sliced = dict(usage)
        sliced["total_tokens"] = total_tokens
        return sliced
    ratio = normalized_billable / total_tokens
    sliced = {
        "input_tokens": math.floor(usage["input_tokens"] * ratio),
        "cached_input_tokens": math.floor(usage["cached_input_tokens"] * ratio),
        "output_tokens": math.floor(usage["output_tokens"] * ratio),
        "reasoning_tokens": math.floor(usage["reasoning_tokens"] * ratio),
        "total_tokens": normalized_billable,
    }
    allocated = (
        sliced["input_tokens"]
        + sliced["cached_input_tokens"]
        + sliced["output_tokens"]
        + sliced["reasoning_tokens"]
    )
    remainder = max(normalized_billable - allocated, 0)
    if remainder > 0:
        sliced["output_tokens"] += remainder
    return sliced


def _surface_minimum(policy: dict[str, Any], surface: str) -> int:
    normalized_surface = str(surface or "").strip()
    if normalized_surface == "mission":
        return _int_policy_value(policy, "min_mission_model_credits", default=10)
    return _int_policy_value(policy, "min_chat_credits", default=3)


def _raw_cost_usd(policy: dict[str, Any], usage: dict[str, int]) -> float:
    raw_cost = policy.get("raw_cost")
    if not isinstance(raw_cost, dict):
        raw_cost = {}
    return (
        usage["input_tokens"] / 1_000_000 * _coerce_float(raw_cost.get("input_usd_per_1m"), default=0)
        + usage["cached_input_tokens"] / 1_000_000 * _coerce_float(raw_cost.get("cached_input_usd_per_1m"), default=0)
        + usage["output_tokens"] / 1_000_000 * _coerce_float(raw_cost.get("output_usd_per_1m"), default=0)
        + usage["reasoning_tokens"] / 1_000_000 * _coerce_float(raw_cost.get("reasoning_usd_per_1m"), default=0)
    )


def _resolve_tier_config(raw_tiers: Any, tier_name: str) -> dict[str, Any]:
    if isinstance(raw_tiers, dict):
        if tier_name and isinstance(raw_tiers.get(tier_name), dict):
            return dict(raw_tiers[tier_name])
        for key, value in raw_tiers.items():
            if isinstance(value, dict):
                config = dict(value)
                config.setdefault("tier", key)
                return config
    if isinstance(raw_tiers, list):
        for item in raw_tiers:
            if isinstance(item, dict) and (not tier_name or item.get("tier") == tier_name):
                return dict(item)
        for item in raw_tiers:
            if isinstance(item, dict):
                return dict(item)
    return {}


def _int_policy_value(policy: dict[str, Any], key: str, *, default: int) -> int:
    return max(_coerce_int(policy.get(key), default=default), 0)


def _float_policy_value(policy: dict[str, Any], key: str, *, default: float) -> float:
    return max(_coerce_float(policy.get(key), default=default), 0)


def _bool_policy_value(policy: dict[str, Any], key: str, *, default: bool) -> bool:
    value = policy.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return max(int(value if value is not None else default), 0)
    except (TypeError, ValueError):
        return max(int(default), 0)


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return max(float(value if value is not None else default), 0)
    except (TypeError, ValueError):
        return max(float(default), 0)
