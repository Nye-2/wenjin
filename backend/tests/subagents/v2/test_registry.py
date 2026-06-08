from __future__ import annotations

import pytest

from src.subagents.v2.registry import (
    agent_template_requires_harness_context,
    normalize_agent_template_tool_affinity,
    validate_agent_template_contract,
)


def test_normalizes_agent_template_tool_affinity_without_widening_business_tools() -> None:
    template = {
        "id": "evidence_analyst.v1",
        "tool_affinity": {
            "preferred": ["document_read", "sandbox_python"],
            "can_request": ["sandbox_exec", "library_read"],
        },
        "risk_profile": {"filesystem": "sandbox_only", "code_execution": "optional"},
    }

    assert normalize_agent_template_tool_affinity(template) == {
        "preferred": ["document_read", "sandbox.run_python"],
        "can_request": ["sandbox.run_python", "library_read"],
    }
    assert agent_template_requires_harness_context(template) is True


def test_validates_agent_template_rejects_retired_sandbox_aliases() -> None:
    errors = validate_agent_template_contract(
        {
            "id": "evidence_analyst.v1",
            "tool_affinity": {"preferred": ["sandbox_python"], "can_request": []},
            "risk_profile": {"filesystem": "sandbox_only", "code_execution": "optional"},
        }
    )

    assert errors == [
        "evidence_analyst.v1: tool_affinity.preferred uses retired harness tool "
        "'sandbox_python'; use 'sandbox.run_python'"
    ]


def test_validates_agent_template_rejects_unknown_tools() -> None:
    errors = validate_agent_template_contract(
        {
            "id": "research_scout.v1",
            "tool_affinity": {"preferred": ["web_search"], "can_request": ["unknown_tool"]},
            "risk_profile": {"filesystem": "no_direct_write", "code_execution": "not_needed"},
        }
    )

    assert errors == [
        "research_scout.v1: tool_affinity.can_request declares unknown team tool 'unknown_tool'"
    ]


@pytest.mark.parametrize(
    "tool_name",
    [
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.register_dataset",
        "sandbox.register_artifact",
    ],
)
def test_validates_agent_template_rejects_write_tool_without_sandbox_filesystem(tool_name: str) -> None:
    errors = validate_agent_template_contract(
        {
            "id": "writer.v1",
            "tool_affinity": {"preferred": [tool_name], "can_request": []},
            "risk_profile": {"filesystem": "no_direct_write", "code_execution": "not_needed"},
        }
    )

    assert errors == [
        "writer.v1: sandbox write tools require risk_profile.filesystem='sandbox_only'"
    ]


def test_validates_agent_template_rejects_python_tool_without_code_execution_profile() -> None:
    errors = validate_agent_template_contract(
        {
            "id": "methodologist.v1",
            "tool_affinity": {"preferred": ["sandbox.run_python"], "can_request": []},
            "risk_profile": {"filesystem": "sandbox_only", "code_execution": "not_needed"},
        }
    )

    assert errors == [
        "methodologist.v1: sandbox.run_python requires "
        "risk_profile.code_execution optional|required"
    ]


def test_validates_agent_template_accepts_read_only_business_roles_without_harness_context() -> None:
    template = {
        "id": "literature_synthesizer.v1",
        "tool_affinity": {
            "preferred": ["library_read", "document_read"],
            "can_request": ["citation_parser", "artifact_create"],
        },
        "risk_profile": {"filesystem": "no_direct_write", "code_execution": "not_needed"},
    }

    assert validate_agent_template_contract(template) == []
    assert agent_template_requires_harness_context(template) is False


@pytest.mark.parametrize(
    "tool_name",
    [
        "sandbox.list_dir",
        "sandbox.glob",
        "sandbox.grep",
        "sandbox.read_file",
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.register_dataset",
        "sandbox.register_artifact",
        "sandbox.run_python",
    ],
)
def test_builtin_sandbox_tool_names_are_known_team_tools(tool_name: str) -> None:
    errors = validate_agent_template_contract(
        {
            "id": "sandbox_member.v1",
            "tool_affinity": {"preferred": [tool_name], "can_request": []},
            "risk_profile": {"filesystem": "sandbox_only", "code_execution": "required"},
        }
    )

    assert errors == []
