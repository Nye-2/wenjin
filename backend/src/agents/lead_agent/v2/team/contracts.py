"""Contracts for Lead Agent team-kernel runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    output_report: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


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
