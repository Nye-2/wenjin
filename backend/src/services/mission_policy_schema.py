"""Validation and resolution for MissionPolicy and WorkerSkill catalog contracts."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from src.contracts.mission_policy import MissionPolicy
from src.contracts.stage_acceptance import StageAcceptanceContract


class ResolvedMissionPolicyBundle(BaseModel):
    """A policy plus the exact content-addressed stage contracts it resolves to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: MissionPolicy
    stage_contracts: tuple[StageAcceptanceContract, ...]

    def to_catalog_data(self) -> dict[str, object]:
        return self.policy.to_catalog_data(resolved_stage_contracts=[contract.model_dump(mode="json", exclude_none=True) for contract in self.stage_contracts])


def resolve_mission_policy_bundle(
    policy: MissionPolicy,
    contracts: Iterable[StageAcceptanceContract],
) -> ResolvedMissionPolicyBundle:
    """Resolve and verify every immutable policy reference, failing closed."""

    contract_list = tuple(contracts)
    contract_by_id = {contract.contract_id: contract for contract in contract_list}
    if len(contract_by_id) != len(contract_list):
        raise ValueError("duplicate stage acceptance contract ids")

    resolved: list[StageAcceptanceContract] = []
    for ref in policy.stage_contract_refs:
        contract = contract_by_id.get(ref.contract_id)
        if contract is None:
            raise ValueError(f"stage contract not found: {ref.contract_id}")
        actual_ref = contract.immutable_ref()
        if ref.schema_version != actual_ref.schema_version or ref.sha256 != actual_ref.sha256:
            raise ValueError(f"stage contract hash/version mismatch: {ref.contract_id}")
        if contract.mission_policy_id != policy.id:
            raise ValueError(f"stage contract {ref.contract_id} belongs to {contract.mission_policy_id}, not {policy.id}")
        if contract.workspace_type != policy.workspace_type:
            raise ValueError(f"stage contract {ref.contract_id} workspace does not match policy")
        resolved.append(contract)

    stage_ids = {contract.stage_id for contract in resolved}
    required_stage_ids = {
        stage_id
        for target in policy.completion_contract.targets.values()
        for stage_id in target.stage_ids
    }
    missing_completion_stages = required_stage_ids - stage_ids
    if missing_completion_stages:
        raise ValueError("completion contract references unknown stages: " + ", ".join(sorted(missing_completion_stages)))

    examples = {example.example_id: example for example in policy.examples}
    for contract in resolved:
        unknown_prerequisites = set(contract.prerequisite_stage_ids) - stage_ids
        if unknown_prerequisites:
            raise ValueError(f"stage {contract.stage_id} has unknown prerequisites: " + ", ".join(sorted(unknown_prerequisites)))
        for exemplar_ref in contract.exemplar_refs:
            example = examples.get(exemplar_ref.ref_id)
            if example is None:
                raise ValueError(f"stage {contract.stage_id} references unknown exemplar {exemplar_ref.ref_id}")
            if example.content_hash() != exemplar_ref.sha256:
                raise ValueError(f"stage {contract.stage_id} exemplar hash mismatch: {exemplar_ref.ref_id}")

    _reject_stage_dependency_cycles(resolved)
    return ResolvedMissionPolicyBundle(policy=policy, stage_contracts=tuple(resolved))


class CrossRefValidator:
    """Catalog cross-reference validation without graph or subagent-template coupling."""

    def __init__(self, *, dataservice: object | None = None) -> None:
        self._dataservice = dataservice

    async def validate_policy(self, policy: MissionPolicy) -> list[str]:
        existing = await self._existing_skill_ids(set(policy.allowed_worker_skills))
        return [f"worker skill '{skill_id}' not found" for skill_id in policy.allowed_worker_skills if skill_id not in existing]

    async def _existing_skill_ids(self, ids: set[str]) -> set[str]:
        if self._dataservice is not None:
            skills = await self._dataservice.list_worker_skills()
            return {skill.id for skill in skills if skill.id in ids}

        from src.dataservice_client.provider import dataservice_client

        async with dataservice_client() as client:
            skills = await client.list_worker_skills()
            return {skill.id for skill in skills if skill.id in ids}


def _reject_stage_dependency_cycles(contracts: list[StageAcceptanceContract]) -> None:
    dependencies = {contract.stage_id: set(contract.prerequisite_stage_ids) for contract in contracts}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visited:
            return
        if stage_id in visiting:
            raise ValueError(f"stage prerequisite cycle detected at {stage_id}")
        visiting.add(stage_id)
        for dependency in dependencies.get(stage_id, set()):
            visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage_id in dependencies:
        visit(stage_id)
