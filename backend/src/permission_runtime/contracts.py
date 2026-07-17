"""Canonical permission and pause contracts for MissionRuntime."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PermissionDecision(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_MISSION = "allow_for_mission"
    REJECT = "reject"
    REVISE_AND_CONTINUE = "revise_and_continue"
    ASK_MORE = "ask_more"
    CANCEL_MISSION = "cancel_mission"


class PermissionContext(_StrictModel):
    mission_id: str = Field(min_length=1, max_length=36)
    tool_name: str = Field(min_length=1, max_length=160)
    operation: str = Field(min_length=1, max_length=160)
    target: str | None = Field(default=None, max_length=2048)
    risk_level: str = Field(pattern="^(low|medium|high)$")
    network_profile: str = Field(default="none", max_length=80)
    secret_access: bool = False
    external_account: bool = False
    billing_scope: str | None = Field(default=None, max_length=160)


class PermissionGrant(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    mission_id: str = Field(min_length=1, max_length=36)
    decision: PermissionDecision
    tool_name: str = Field(min_length=1, max_length=160)
    operation: str = Field(min_length=1, max_length=160)
    network_profile: str = Field(default="none", max_length=80)

    @model_validator(mode="after")
    def validate_allow(self) -> PermissionGrant:
        if self.decision not in {
            PermissionDecision.ALLOW_ONCE,
            PermissionDecision.ALLOW_FOR_MISSION,
        }:
            raise ValueError("PermissionGrant requires an allow decision")
        return self


class PermissionResolution(_StrictModel):
    request_id: str
    decision: PermissionDecision
    resumed: bool
    grant: PermissionGrant | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)


__all__ = [name for name in globals() if name.startswith("Permission")]
