from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.workspace_agent.contracts import (
    AgentActionAdapter,
    MissionInputKind,
    StartMissionAction,
)


def _mission_payload() -> dict[str, object]:
    return {
        "workspace_id": "workspace-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "workspace_type": "sci",
        "raw_user_message_id": "message-1",
        "mission_idempotency_key": "thread-1:message-1:start",
        "objective": "梳理联邦学习与大模型微调的研究空白",
        "mission_policy_id": "sci.research",
        "initial_params": [{"key": "topic", "value": "federated fine-tuning"}],
        "review_mode": "balanced_default",
        "model_id": "gpt-5.5",
        "reasoning_effort": "xhigh",
        "model_capability_profile_hash": "sha256:profile-v1",
        "runtime_context_refs": ["prompt:workspace-agent-v1"],
    }


def test_start_mission_action_is_strict_and_typed() -> None:
    action = AgentActionAdapter.validate_python(
        {"action": "start_mission", "mission": _mission_payload()}
    )

    assert isinstance(action, StartMissionAction)
    assert action.mission.reasoning_effort == "xhigh"
    assert action.mission.objective == "梳理联邦学习与大模型微调的研究空白"


def test_action_contract_rejects_old_launcher_fields() -> None:
    payload = _mission_payload()
    payload["feature_id"] = "old-feature"

    with pytest.raises(ValidationError, match="feature_id"):
        AgentActionAdapter.validate_python(
            {"action": "start_mission", "mission": payload}
        )


def test_action_contract_rejects_unsupported_reasoning_effort() -> None:
    payload = _mission_payload()
    payload["reasoning_effort"] = "minimal"

    with pytest.raises(ValidationError):
        AgentActionAdapter.validate_python(
            {"action": "start_mission", "mission": payload}
        )


def test_active_mission_input_uses_explicit_semantic_kind() -> None:
    action = AgentActionAdapter.validate_python(
        {
            "action": "steer_mission",
            "mission_id": "mission-1",
            "command_id": "command-1",
            "input_kind": "correction",
            "instruction": "不要保存，先补强证据。",
        }
    )

    assert action.input_kind is MissionInputKind.CORRECTION


def test_unknown_agent_action_fails_closed() -> None:
    with pytest.raises(ValidationError):
        AgentActionAdapter.validate_python(
            {"action": "write_room_directly", "room": "documents"}
        )
