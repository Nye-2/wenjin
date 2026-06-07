from __future__ import annotations

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext, HarnessToolSpec
from src.agents.harness.policy import resolve_harness_policy
from src.agents.harness.tool_registry import HarnessToolRegistry, UnknownHarnessToolError
from src.sandbox.workspace_layout import WORKSPACE_PROTECTED_PATHS


def _ctx(
    *,
    capability_policy: dict | None = None,
    template: dict | None = None,
    skill: dict | None = None,
) -> HarnessRunContext:
    return HarnessRunContext(
        workspace_id="workspace-1",
        user_id="user-1",
        execution_id="execution-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
        capability_policy=capability_policy or {},
        agent_template=template or {},
        skill=skill or {},
        context_bundle={},
    )


def test_policy_uses_capability_as_maximum_permission_envelope() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={
                "allowed_tools": ["sandbox.read_file", "sandbox.write_file"],
                "permissions": ["filesystem.read", "filesystem.write"],
            },
            template={"tool_affinity": {"preferred": ["sandbox.read_file", "sandbox.run_python"]}},
            skill={"allowed_tools": ["sandbox.read_file", "sandbox.run_python"]},
        )
    )

    assert policy.allowed_tools == ("sandbox.read_file",)
    assert policy.permissions == frozenset({"filesystem.read"})
    assert "sandbox.run_python" in policy.denied_tools


def test_policy_defaults_to_read_only_baseline_for_omitted_skill_tools() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={
                "allowed_tools": ["sandbox.read_file", "sandbox.write_file", "sandbox.run_python"],
                "permissions": [
                    "filesystem.read",
                    "filesystem.write",
                    "sandbox.run_python",
                ],
            },
            skill={},
        )
    )

    assert policy.allowed_tools == ("sandbox.read_file",)
    assert policy.permissions == frozenset({"filesystem.read"})


def test_policy_derives_sandbox_tools_from_skill_sandbox_access() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={
                "sandbox_policy": {
                    "allowed_operations": ["run_python", "install_python_packages"],
                },
            },
            template={"tool_affinity": {"preferred": ["sandbox.run_python"]}},
            skill={
                "allowed_tools": [],
                "skill_json": {
                    "sandbox_access": {"mode": "optional", "profiles": ["analysis"]},
                },
            },
        )
    )

    assert policy.allowed_tools == ("sandbox.run_python",)
    assert policy.permissions == frozenset({"sandbox.run_python"})


def test_policy_canonicalizes_existing_sandbox_python_alias() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={"allowed_tools": ["sandbox_python"]},
            template={"tool_affinity": {"preferred": ["sandbox_python"]}},
            skill={
                "skill_json": {
                    "sandbox_access": {"mode": "required", "profiles": ["analysis"]},
                },
            },
        )
    )

    assert policy.allowed_tools == ("sandbox.run_python",)


def test_policy_uses_workspace_layout_protected_paths() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={"allowed_tools": ["sandbox.read_file"]},
            skill={"allowed_tools": ["sandbox.read_file"]},
        )
    )

    assert policy.protected_paths == WORKSPACE_PROTECTED_PATHS


def test_harness_policy_defaults_to_workspace_layout_protected_paths() -> None:
    policy = HarnessPolicy()

    assert policy.protected_paths == WORKSPACE_PROTECTED_PATHS


def test_registry_rejects_duplicate_tool_names() -> None:
    read_spec = HarnessToolSpec(
        name="sandbox.read_file",
        namespace="sandbox",
        description="Read a file",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    )

    with pytest.raises(ValueError, match="duplicate harness tool"):
        HarnessToolRegistry([read_spec, read_spec])


def test_registry_resolves_known_tools_and_fails_unknown_names() -> None:
    spec = HarnessToolSpec(
        name="sandbox.read_file",
        namespace="sandbox",
        description="Read a file",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    )
    registry = HarnessToolRegistry([spec])

    assert registry.get("sandbox.read_file") == spec
    with pytest.raises(UnknownHarnessToolError, match="unknown harness tool"):
        registry.get("sandbox.run_command")
