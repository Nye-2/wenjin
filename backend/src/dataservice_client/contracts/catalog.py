"""Wire contracts for MissionPolicy and WorkerSkill catalog."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.contracts.mission_policy import MissionPolicy, WorkerSkill


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionPolicyPayload(_Strict):
    id: str
    workspace_type: str
    schema_version: str
    enabled: bool
    policy_json: dict[str, Any]
    content_hash: str = Field(min_length=64, max_length=64)
    source_path: str | None = None

    @model_validator(mode="after")
    def validate_canonical_policy(self) -> MissionPolicyPayload:
        raw = dict(self.policy_json)
        raw.pop("resolved_stage_contracts", None)
        embedded_hash = str(raw.pop("content_hash", "") or "")
        policy = MissionPolicy.model_validate(raw)
        if policy.id != self.id or policy.workspace_type != self.workspace_type or policy.schema_version != self.schema_version or policy.enabled != self.enabled:
            raise ValueError("MissionPolicy payload index fields do not match policy_json")
        if embedded_hash != self.content_hash or policy.immutable_ref().sha256 != self.content_hash:
            raise ValueError("MissionPolicy payload content_hash is inconsistent")
        return self

    def to_contract(self) -> MissionPolicy:
        raw = dict(self.policy_json)
        raw.pop("resolved_stage_contracts", None)
        raw.pop("content_hash", None)
        return MissionPolicy.model_validate(raw)


class WorkerSkillPayload(_Strict):
    id: str
    schema_version: str
    enabled: bool
    skill_json: dict[str, Any]
    content_hash: str = Field(min_length=64, max_length=64)
    source_path: str | None = None

    @model_validator(mode="after")
    def validate_canonical_skill(self) -> WorkerSkillPayload:
        raw = dict(self.skill_json)
        embedded_hash = str(raw.pop("content_hash", "") or "")
        skill = WorkerSkill.model_validate(raw)
        if skill.id != self.id or skill.schema_version != self.schema_version or skill.enabled != self.enabled:
            raise ValueError("WorkerSkill payload index fields do not match skill_json")
        if embedded_hash != self.content_hash or skill.immutable_ref().sha256 != self.content_hash:
            raise ValueError("WorkerSkill payload content_hash is inconsistent")
        return self

    def to_contract(self) -> WorkerSkill:
        raw = dict(self.skill_json)
        raw.pop("content_hash", None)
        return WorkerSkill.model_validate(raw)


class CatalogSeedItemPayload(_Strict):
    data: dict[str, Any]
    source_path: str | None = None


class CatalogSeedLoadPayload(_Strict):
    overwrite: bool = False
    items: list[CatalogSeedItemPayload] = Field(default_factory=list)


class CatalogSeedLoadResultPayload(_Strict):
    loaded: int
