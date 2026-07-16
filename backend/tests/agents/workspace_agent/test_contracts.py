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
        "title": "联邦学习研究空白",
        "objective": "梳理联邦学习与大模型微调的研究空白",
        "mission_policy_id": "sci.research",
        "initial_params": [{"key": "topic", "value": "federated fine-tuning"}],
    }


def test_start_mission_action_is_strict_and_typed() -> None:
    action = AgentActionAdapter.validate_python(
        {"action": "start_mission", "mission": _mission_payload()}
    )

    assert isinstance(action, StartMissionAction)
    assert action.mission.title == "联邦学习研究空白"
    assert action.mission.objective == "梳理联邦学习与大模型微调的研究空白"


def test_action_contract_rejects_old_launcher_fields() -> None:
    payload = _mission_payload()
    payload["feature_id"] = "old-feature"

    with pytest.raises(ValidationError, match="feature_id"):
        AgentActionAdapter.validate_python(
            {"action": "start_mission", "mission": payload}
        )


def test_action_contract_rejects_server_owned_fields() -> None:
    payload = _mission_payload()
    payload["user_id"] = "provider-controlled-user"

    with pytest.raises(ValidationError, match="user_id"):
        AgentActionAdapter.validate_python(
            {"action": "start_mission", "mission": payload}
        )

    payload = _mission_payload()
    payload["review_mode"] = "review_all"

    with pytest.raises(ValidationError, match="review_mode"):
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
