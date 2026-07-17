"""Canonical cumulative resource accounting for one durable Mission."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.contracts.model_usage import ModelUsage


class MissionExecutionBudget(BaseModel):
    """Pinned dispatch ceilings plus a post-response token stop threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_calls: int = Field(ge=1, le=10_000)
    max_tool_operations: int = Field(ge=0, le=20_000)
    max_subagent_jobs: int = Field(ge=0, le=2_000)
    stop_after_total_tokens: int = Field(ge=1, le=100_000_000)


class MissionResourceUsage(BaseModel):
    """DataService-owned cumulative usage projection for one Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls: int = Field(default=0, ge=0)
    tool_operations: int = Field(default=0, ge=0)
    subagent_jobs: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_token_subsets(self) -> MissionResourceUsage:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens must be a subset of input_tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning_tokens must be a subset of output_tokens")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be smaller than input plus output")
        return self

    def add(self, other: MissionResourceUsage) -> MissionResourceUsage:
        return MissionResourceUsage(
            **{
                field: int(getattr(self, field)) + int(getattr(other, field))
                for field in type(self).model_fields
            }
        )

    def token_usage(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


def execution_budget_from_runtime_context(
    runtime_context: dict[str, Any],
) -> MissionExecutionBudget:
    raw_policy = runtime_context.get("mission_policy_snapshot")
    if not isinstance(raw_policy, dict):
        raise ValueError("pinned MissionPolicy snapshot is required")
    raw_budget = raw_policy.get("execution_budget")
    if not isinstance(raw_budget, dict):
        raise ValueError("pinned Mission execution budget is required")
    return MissionExecutionBudget.model_validate(raw_budget)


def resource_usage_from_snapshot(snapshot: dict[str, Any]) -> MissionResourceUsage:
    raw = snapshot.get("resource_usage")
    if raw is None:
        return MissionResourceUsage()
    if not isinstance(raw, dict):
        raise ValueError("Mission resource_usage must be an object")
    return MissionResourceUsage.model_validate(raw)


def snapshot_with_resource_usage(
    snapshot: dict[str, Any],
    usage: MissionResourceUsage,
) -> dict[str, Any]:
    projected = dict(snapshot)
    projected["resource_usage"] = usage.model_dump(mode="json")
    return projected


def resource_delta_for_item(
    *,
    item_type: str,
    payload_json: dict[str, Any],
) -> MissionResourceUsage:
    if item_type == "model_call_started":
        return MissionResourceUsage(model_calls=1)
    if item_type == "operation_claim":
        return MissionResourceUsage(tool_operations=1)
    if item_type == "subagent_spawned":
        input_scope = payload_json.get("input_scope")
        raw_jobs = input_scope.get("jobs") if isinstance(input_scope, dict) else None
        job_count = len(raw_jobs) if isinstance(raw_jobs, list) and raw_jobs else 1
        return MissionResourceUsage(subagent_jobs=job_count)
    if item_type == "usage_receipt":
        raw_usage = payload_json.get("usage")
        usage = ModelUsage.model_validate(raw_usage) if isinstance(raw_usage, dict) else ModelUsage()
        return MissionResourceUsage(**usage.model_dump(mode="python"))
    return MissionResourceUsage()


def exceeded_budget_dimensions(
    usage: MissionResourceUsage,
    budget: MissionExecutionBudget,
) -> tuple[str, ...]:
    exceeded: list[str] = []
    if usage.model_calls > budget.max_model_calls:
        exceeded.append("model_calls")
    if usage.tool_operations > budget.max_tool_operations:
        exceeded.append("tool_operations")
    if usage.subagent_jobs > budget.max_subagent_jobs:
        exceeded.append("subagent_jobs")
    if usage.total_tokens > budget.stop_after_total_tokens:
        exceeded.append("total_tokens")
    return tuple(exceeded)


def unavailable_budget_dimensions(
    usage: MissionResourceUsage,
    budget: MissionExecutionBudget,
    *,
    model_calls: int = 0,
    tool_operations: int = 0,
    subagent_jobs: int = 0,
) -> tuple[str, ...]:
    requested = usage.add(
        MissionResourceUsage(
            model_calls=model_calls,
            tool_operations=tool_operations,
            subagent_jobs=subagent_jobs,
        )
    )
    unavailable: list[str] = []
    if requested.model_calls > budget.max_model_calls:
        unavailable.append("model_calls")
    if requested.tool_operations > budget.max_tool_operations:
        unavailable.append("tool_operations")
    if requested.subagent_jobs > budget.max_subagent_jobs:
        unavailable.append("subagent_jobs")
    if usage.total_tokens >= budget.stop_after_total_tokens:
        unavailable.append("total_tokens")
    return tuple(unavailable)


__all__ = [
    "MissionExecutionBudget",
    "MissionResourceUsage",
    "exceeded_budget_dimensions",
    "execution_budget_from_runtime_context",
    "resource_delta_for_item",
    "resource_usage_from_snapshot",
    "snapshot_with_resource_usage",
    "unavailable_budget_dimensions",
]
