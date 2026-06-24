"""Contracts for Lead Agent team-kernel runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentTemplate(BaseModel):
    id: str
    schema_version: str = "agent_template.v1"
    enabled: bool = True
    display_role: str
    category: str
    description: str = ""
    persona_prompt: str = ""
    default_skills: list[str] = Field(default_factory=list)
    tool_affinity: dict[str, Any] = Field(default_factory=dict)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    output_contracts: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    runtime_defaults: dict[str, Any] = Field(default_factory=dict)
    expert_profile: dict[str, Any] = Field(default_factory=dict)


class TeamLimits(BaseModel):
    max_iterations: int = Field(default=5, ge=1, le=8)
    max_parallel_invocations: int = Field(default=3, ge=1, le=5)
    max_invocations_total: int = Field(default=12, ge=1, le=24)
    max_invocations_per_template: int = Field(default=3, ge=1, le=6)
    no_progress_rounds_before_stop: int = Field(default=2, ge=1, le=4)


class TeamBudget(BaseModel):
    max_tokens_soft: int | None = Field(default=None, ge=1)
    max_tokens_hard: int | None = Field(default=None, ge=1)
    max_sandbox_seconds: int | None = Field(default=None, ge=1)


class CapabilityTeamPolicy(BaseModel):
    core_templates: list[str] = Field(default_factory=list)
    optional_templates: list[str] = Field(default_factory=list)
    recruitment_triggers: dict[str, Any] = Field(default_factory=dict)
    quality_pipeline: list[str] = Field(default_factory=list)
    limits: TeamLimits = Field(default_factory=TeamLimits)
    budget: TeamBudget = Field(default_factory=TeamBudget)
    capability_tools: list[str] = Field(default_factory=list)
    workspace_tools: list[str] = Field(default_factory=list)
    user_tools: list[str] = Field(default_factory=list)
    capability_skills: list[str] = Field(default_factory=list)
    contract_overlay_skills: list[str] = Field(default_factory=list)
    contract_overlay_categories: list[str] = Field(default_factory=list)
    template_profile_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("core_templates", "optional_templates")
    @classmethod
    def _dedupe_template_list(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            key = str(item).strip()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result

    @field_validator(
        "capability_tools",
        "workspace_tools",
        "user_tools",
        "capability_skills",
        "contract_overlay_skills",
        "contract_overlay_categories",
    )
    @classmethod
    def _dedupe_string_list(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            key = str(item).strip()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result


class AgentInvocation(BaseModel):
    id: str
    execution_id: str | None = None
    iteration: int
    template_id: str
    display_name: str
    assigned_role: str
    recruitment_reason: str
    input_brief: dict[str, Any] = Field(default_factory=dict)
    effective_tools: list[str] = Field(default_factory=list)
    effective_skills: list[str] = Field(default_factory=list)
    expert_profile: dict[str, Any] = Field(default_factory=dict)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    output_report: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    completed_at: datetime | None = None
    expert_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    expert_preview_items: list[dict[str, Any]] = Field(default_factory=list)


class HarnessReplanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default="wenjin.team.harness_replan_decision.v1", alias="schema")
    iteration: int
    phase: str
    gate_ids: list[str] = Field(default_factory=list)
    gate_statuses: list[str] = Field(default_factory=list)
    next_action: str = ""
    selected_recruits: list[str] = Field(default_factory=list)


class HarnessEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default="wenjin.team.harness_episode.v1", alias="schema")
    execution_id: str
    status: Literal["running", "finished"] = "running"
    core_templates: list[str] = Field(default_factory=list)
    decisions: list[HarnessReplanDecision] = Field(default_factory=list)
    stop_reason: str = ""


class TeamBlackboard(BaseModel):
    mission_summary: str = ""
    confirmed_findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    citation_gaps: list[dict[str, Any]] = Field(default_factory=list)
    experiment_gaps: list[dict[str, Any]] = Field(default_factory=list)
    data_gaps: list[dict[str, Any]] = Field(default_factory=list)
    figure_table_requirements: list[dict[str, Any]] = Field(default_factory=list)
    writing_risks: list[dict[str, Any]] = Field(default_factory=list)
    format_risks: list[dict[str, Any]] = Field(default_factory=list)
    pending_decisions: list[dict[str, Any]] = Field(default_factory=list)
    rejected_claims: list[dict[str, Any]] = Field(default_factory=list)
    quality_gate_history: list[dict[str, Any]] = Field(default_factory=list)
    harness_replan_signals: list[dict[str, Any]] = Field(default_factory=list)
    harness_episode: HarnessEpisode | None = None
    latest_leader_summary: str = ""


class QualityGateResult(BaseModel):
    gate_id: str
    status: Literal["pass", "warning", "fail"]
    severity: Literal["low", "medium", "high"] = "low"
    findings: list[dict[str, Any]] = Field(default_factory=list)
    required_fixes: list[dict[str, Any]] = Field(default_factory=list)
    suggested_recruits: list[dict[str, Any]] = Field(default_factory=list)
    next_action: Literal[
        "finish",
        "revise_existing",
        "recruit_more",
        "ask_user",
        "stop_with_warning",
    ] = "finish"
