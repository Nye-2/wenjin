from __future__ import annotations

import pytest

from src.sandbox.workspace_layout import (
    WORKSPACE_LAYOUT_VERSION,
    WORKSPACE_STANDARD_DIRS,
    build_agent_workspace_contract,
    build_workspace_task_contract,
    is_user_reviewable_workspace_artifact_path,
    is_workspace_protected_path,
    workspace_task_scratch_path,
    workspace_virtual_path,
)


def test_public_layout_has_no_control_or_environment_directory() -> None:
    assert WORKSPACE_LAYOUT_VERSION == 2
    assert WORKSPACE_STANDARD_DIRS == (
        "main",
        "datasets",
        "scripts",
        "outputs",
        "reports",
        "tmp",
    )
    assert all(".wenjin" not in path for path in WORKSPACE_STANDARD_DIRS)


def test_task_scratch_uses_mission_and_item_or_subagent_identity() -> None:
    assert (
        workspace_task_scratch_path(
            mission_id="mission-1",
            mission_item_seq=8,
        )
        == "/workspace/tmp/tasks/mission-1/item-8"
    )
    assert (
        workspace_task_scratch_path(
            mission_id="mission-1",
            mission_item_seq=8,
            subagent_id="analysis-1",
        )
        == "/workspace/tmp/tasks/mission-1/analysis-1"
    )
    contract = build_workspace_task_contract(
        mission_id="mission-1",
        mission_item_seq=8,
        subagent_id="analysis-1",
    )
    serialized = str(contract)
    assert "execution_id" not in serialized
    assert "node_id" not in serialized


def test_agent_contract_exposes_typed_operations_without_shell() -> None:
    contract = build_agent_workspace_contract()

    assert contract["default_network_profile"] == "none"
    assert "sandbox.run_python" in contract["typed_operations"]
    assert "sandbox.install_dependencies" in contract["typed_operations"]
    assert all("shell" not in operation for operation in contract["typed_operations"])


@pytest.mark.parametrize(
    "path",
    [
        "/workspace/.wenjin/manifest.json",
        "/workspace/main/.env",
        "/workspace/main/private.key",
    ],
)
def test_control_and_secret_like_paths_are_protected(path: str) -> None:
    assert is_workspace_protected_path(path)


def test_only_outputs_and_reports_are_reviewable_artifacts() -> None:
    assert is_user_reviewable_workspace_artifact_path("/workspace/outputs/chart.png")
    assert is_user_reviewable_workspace_artifact_path("/workspace/reports/analysis.md")
    assert not is_user_reviewable_workspace_artifact_path("/workspace/scripts/analysis.py")
    assert not is_user_reviewable_workspace_artifact_path("/workspace/tmp/stdout.txt")


def test_workspace_virtual_path_rejects_parent_traversal() -> None:
    assert workspace_virtual_path("reports/result.md") == "/workspace/reports/result.md"
    with pytest.raises(ValueError):
        workspace_virtual_path("../outside")
