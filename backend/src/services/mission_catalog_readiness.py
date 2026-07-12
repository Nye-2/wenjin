"""Pure readiness evaluation for the deployed Mission catalog."""

from __future__ import annotations

from typing import Any, get_args

from src.contracts.stage_acceptance import WorkspaceType
from src.services.search.model_native import native_search_capability


def evaluate_mission_catalog_readiness(
    policies: list[Any],
    skills: list[Any],
    *,
    mission_model: Any | None,
) -> dict[str, Any]:
    required = set(get_args(WorkspaceType))
    skill_ids = {item.id for item in skills}
    workspace_types = {item.workspace_type for item in policies}
    missing_refs: dict[str, list[str]] = {}
    contracts = []
    for record in policies:
        contract = record.to_contract()
        contracts.append((record, contract))
        missing = sorted(set(contract.allowed_worker_skills) - skill_ids)
        if missing:
            missing_refs[record.id] = missing
    missing_workspaces = sorted(required - workspace_types)
    if missing_workspaces or missing_refs or not skills:
        return {
            "status": "unhealthy",
            "missing_workspace_types": missing_workspaces,
            "missing_worker_skills": missing_refs,
            "policy_count": len(policies),
            "skill_count": len(skills),
        }

    search_policies = [
        record.id
        for record, contract in contracts
        if "model_native_web_search" in contract.tool_policy.allowed_tool_groups
    ]
    if search_policies:
        if mission_model is None:
            return {
                "status": "unhealthy",
                "error": "default Mission model is not loaded",
                "search_policy_ids": search_policies,
            }
        search = native_search_capability(mission_model)
        if not search.available:
            return {
                "status": "unhealthy",
                "error": "enabled MissionPolicy requires unverified native search",
                "search_policy_ids": search_policies,
                "reason_codes": list(search.reason_codes),
            }
    return {
        "status": "healthy",
        "policy_count": len(policies),
        "skill_count": len(skills),
        "workspace_types": sorted(workspace_types),
    }


__all__ = ["evaluate_mission_catalog_readiness"]
