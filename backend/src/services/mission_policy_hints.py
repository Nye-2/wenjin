"""Versioned MissionPolicy routing context for WorkspaceAgent turns."""

from __future__ import annotations

from src.agents.workspace_agent.contracts import MissionPolicyHint
from src.dataservice_client import AsyncDataServiceClient


async def load_mission_policy_hints(
    dataservice: AsyncDataServiceClient,
    workspace_type: str,
) -> tuple[MissionPolicyHint, ...]:
    """Project enabled DataService policies; seed files are never runtime truth."""
    records = await dataservice.list_mission_policies(
        workspace_type=workspace_type,
        enabled_only=True,
    )
    hints: list[MissionPolicyHint] = []
    for record in records:
        policy = record.to_contract()
        if policy.visibility != "route_hint":
            continue
        required = tuple(
            key
            for key, value in policy.minimum_context.items()
            if value.requirement == "required"
        )
        hints.append(
            MissionPolicyHint(
                policy_id=policy.id,
                content_hash=record.content_hash,
                display_name=policy.display.name,
                summary=policy.display.description,
                positive_examples=policy.routing.positive_examples[:4],
                negative_examples=policy.routing.negative_examples[:4],
                required_context=required[:8],
                completion_targets={
                    target_id: target.stage_ids
                    for target_id, target in policy.completion_contract.targets.items()
                },
                default_completion_target=policy.completion_contract.default_target,
            )
        )
    return tuple(hints[:24])


__all__ = ["load_mission_policy_hints"]
