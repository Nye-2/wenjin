"""Pure credit pricing calculations shared across process boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FreeTokenAllowance:
    """Cumulative free-token allowance for one usage surface."""

    enabled: bool
    free_tokens: int

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "enabled": self.enabled,
            "free_tokens": self.free_tokens,
        }


@dataclass(frozen=True, slots=True)
class FreeTokenUsage:
    """Free and billable token slices for one usage event."""

    free_tokens_applied: int
    billable_tokens: int
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
class ChatTurnAuthorizationQuote:
    """Bounded financial hold for one chat turn."""

    token_envelope: int
    free_token_hold: int
    billable_token_envelope: int
    uncapped_credit_ceiling: int
    credit_limit: int
    credit_hold: int

    def as_dict(self) -> dict[str, int]:
        return {
            "token_envelope": self.token_envelope,
            "free_token_hold": self.free_token_hold,
            "billable_token_envelope": self.billable_token_envelope,
            "uncapped_credit_ceiling": self.uncapped_credit_ceiling,
            "credit_limit": self.credit_limit,
            "credit_hold": self.credit_hold,
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


def calculate_free_token_usage(
    *,
    allowance: FreeTokenAllowance,
    total_tokens: int,
    historical_tokens_before: int,
) -> FreeTokenUsage:
    """Slice usage under a cumulative free-token allowance."""
    normalized_total = max(int(total_tokens or 0), 0)
    historical_before = max(int(historical_tokens_before or 0), 0)
    historical_after = historical_before + normalized_total

    if normalized_total <= 0:
        return FreeTokenUsage(
            free_tokens_applied=0,
            billable_tokens=0,
            historical_tokens_after=historical_after,
        )
    if not allowance.enabled:
        return FreeTokenUsage(
            free_tokens_applied=0,
            billable_tokens=normalized_total,
            historical_tokens_after=historical_after,
        )

    overage_before = max(historical_before - allowance.free_tokens, 0)
    overage_after = max(historical_after - allowance.free_tokens, 0)
    billable_tokens = max(overage_after - overage_before, 0)
    free_tokens_applied = max(normalized_total - billable_tokens, 0)
    return FreeTokenUsage(
        free_tokens_applied=free_tokens_applied,
        billable_tokens=billable_tokens,
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

    partitions = _partition_usage(usage)
    return (
        partitions["uncached_input_tokens"] * input_weight
        + partitions["cached_input_tokens"] * cached_input_weight
        + partitions["visible_output_tokens"] * output_weight
        + partitions["reasoning_tokens"] * reasoning_weight
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


def calculate_chat_turn_authorization(
    *,
    model_policy: Any,
    global_policy: Any | None,
    historical_tokens: int,
    reserved_free_tokens: int,
) -> ChatTurnAuthorizationQuote:
    """Price the maximum charge that may be settled for one chat turn."""

    policy = _policy_config(model_policy)
    token_envelope = _int_policy_value(
        policy,
        "chat_turn_token_reserve",
        default=65_536,
    )
    free_tokens = _int_policy_value(policy, "free_tokens", default=0)
    remaining_free_tokens = max(
        free_tokens
        - max(int(historical_tokens or 0), 0)
        - max(int(reserved_free_tokens or 0), 0),
        0,
    )
    free_token_hold = min(remaining_free_tokens, token_envelope)
    billable_token_envelope = max(token_envelope - free_token_hold, 0)
    uncapped_credit_ceiling = calculate_model_usage_credit_ceiling(
        model_policy=policy,
        global_policy=global_policy,
        token_limit=billable_token_envelope,
        surface="chat",
    )
    credit_limit = _int_policy_value(
        policy,
        "chat_turn_max_credits",
        default=100,
    )
    return ChatTurnAuthorizationQuote(
        token_envelope=token_envelope,
        free_token_hold=free_token_hold,
        billable_token_envelope=billable_token_envelope,
        uncapped_credit_ceiling=uncapped_credit_ceiling,
        credit_limit=credit_limit,
        credit_hold=min(uncapped_credit_ceiling, credit_limit),
    )


def calculate_model_usage_credit_ceiling(
    *,
    model_policy: Any,
    global_policy: Any | None,
    token_limit: int,
    surface: str,
) -> int:
    """Return the worst charge over every valid token-detail partition."""

    normalized_limit = max(int(token_limit or 0), 0)
    if normalized_limit <= 0:
        return 0
    scenarios = (
        {
            "input_tokens": normalized_limit,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": normalized_limit,
        },
        {
            "input_tokens": normalized_limit,
            "cached_input_tokens": normalized_limit,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": normalized_limit,
        },
        {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": normalized_limit,
            "reasoning_tokens": 0,
            "total_tokens": normalized_limit,
        },
        {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": normalized_limit,
            "reasoning_tokens": normalized_limit,
            "total_tokens": normalized_limit,
        },
    )
    return max(
        calculate_model_usage_credits(
            model_policy=model_policy,
            global_policy=global_policy,
            token_usage=usage,
            surface=surface,
        ).credits_to_charge
        for usage in scenarios
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
        total_tokens = input_tokens + output_tokens
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
        "output_tokens": math.floor(usage["output_tokens"] * ratio),
        "total_tokens": normalized_billable,
    }
    allocated = sliced["input_tokens"] + sliced["output_tokens"]
    remainder = max(normalized_billable - allocated, 0)
    if remainder > 0:
        sliced["output_tokens"] += remainder
    sliced["cached_input_tokens"] = min(
        math.floor(usage["cached_input_tokens"] * ratio),
        sliced["input_tokens"],
    )
    sliced["reasoning_tokens"] = min(
        math.floor(usage["reasoning_tokens"] * ratio),
        sliced["output_tokens"],
    )
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
    partitions = _partition_usage(usage)
    return (
        partitions["uncached_input_tokens"]
        / 1_000_000
        * _coerce_float(raw_cost.get("input_usd_per_1m"), default=0)
        + partitions["cached_input_tokens"]
        / 1_000_000
        * _coerce_float(raw_cost.get("cached_input_usd_per_1m"), default=0)
        + partitions["visible_output_tokens"]
        / 1_000_000
        * _coerce_float(raw_cost.get("output_usd_per_1m"), default=0)
        + partitions["reasoning_tokens"]
        / 1_000_000
        * _coerce_float(raw_cost.get("reasoning_usd_per_1m"), default=0)
    )


def _partition_usage(usage: dict[str, int]) -> dict[str, int]:
    cached_input = min(usage["cached_input_tokens"], usage["input_tokens"])
    reasoning = min(usage["reasoning_tokens"], usage["output_tokens"])
    return {
        "uncached_input_tokens": usage["input_tokens"] - cached_input,
        "cached_input_tokens": cached_input,
        "visible_output_tokens": usage["output_tokens"] - reasoning,
        "reasoning_tokens": reasoning,
    }


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
