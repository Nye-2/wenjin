from __future__ import annotations

import pytest

from src.subagents.v2.registry import (
    agent_template_requires_harness_context,
    normalize_agent_template_tool_affinity,
    validate_agent_template_contract,
)


def _valid_persona_prompt() -> str:
    return """You are a focused academic support specialist.

Role Boundary:
Stay within the assigned expert role and do not claim to commit canonical workspace state.

Evidence Rules:
Ground claims in supplied sources or mark uncertainty explicitly.
"""


def _template_with_valid_persona(**overrides):
    template = {"persona_prompt": _valid_persona_prompt()}
    template.update(overrides)
    return template


def test_normalizes_agent_template_tool_affinity_without_widening_business_tools() -> None:
    template = {
        "id": "evidence_analyst.v1",
        "tool_affinity": {
            "preferred": ["prism_file_read", "sandbox_python"],
            "can_request": ["sandbox_exec", "library_read"],
        },
        "risk_profile": {"filesystem": "sandbox_only", "code_execution": "optional"},
    }

    assert normalize_agent_template_tool_affinity(template) == {
        "preferred": ["prism_file_read", "sandbox.run_python"],
        "can_request": ["sandbox.run_python", "library_read"],
    }
    assert agent_template_requires_harness_context(template) is True


def test_validates_agent_template_rejects_retired_sandbox_aliases() -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="evidence_analyst.v1",
            tool_affinity={"preferred": ["sandbox_python"], "can_request": []},
            risk_profile={"filesystem": "sandbox_only", "code_execution": "optional"},
        )
    )

    assert errors == [
        "evidence_analyst.v1: tool_affinity.preferred uses retired harness tool "
        "'sandbox_python'; use 'sandbox.run_python'"
    ]


def test_validates_agent_template_rejects_unknown_tools() -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="research_scout.v1",
            tool_affinity={"preferred": ["web_search"], "can_request": ["unknown_tool"]},
            risk_profile={"filesystem": "no_direct_write", "code_execution": "not_needed"},
        )
    )

    assert errors == [
        "research_scout.v1: tool_affinity.can_request declares unknown team tool 'unknown_tool'"
    ]


@pytest.mark.parametrize(
    "tool_name",
    [
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.apply_patch",
        "sandbox.register_dataset",
        "sandbox.register_artifact",
    ],
)
def test_validates_agent_template_rejects_write_tool_without_sandbox_filesystem(tool_name: str) -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="writer.v1",
            tool_affinity={"preferred": [tool_name], "can_request": []},
            risk_profile={"filesystem": "no_direct_write", "code_execution": "not_needed"},
        )
    )

    assert errors == [
        "writer.v1: sandbox write tools require risk_profile.filesystem='sandbox_only'"
    ]


@pytest.mark.parametrize("tool_name", ["sandbox.run_python", "sandbox.generate_figure"])
def test_validates_agent_template_rejects_execute_tool_without_code_execution_profile(
    tool_name: str,
) -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="methodologist.v1",
            tool_affinity={"preferred": [tool_name], "can_request": []},
            risk_profile={"filesystem": "sandbox_only", "code_execution": "not_needed"},
        )
    )

    assert errors == [
        "methodologist.v1: sandbox execute tools require "
        "risk_profile.code_execution optional|required"
    ]


def test_validates_agent_template_accepts_read_only_business_roles_without_harness_context() -> None:
    template = {
        "id": "literature_synthesizer.v1",
        "persona_prompt": _valid_persona_prompt(),
        "tool_affinity": {
            "preferred": ["library_read", "prism_file_read"],
            "can_request": ["citation_parser", "artifact_create"],
        },
        "risk_profile": {"filesystem": "no_direct_write", "code_execution": "not_needed"},
    }

    assert validate_agent_template_contract(template) == []
    assert agent_template_requires_harness_context(template) is False


def test_validates_public_text_allows_non_internal_version_suffix() -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="public_version_helper.v1",
            expert_profile={
                "public_name": "Protocol.V1 Reviewer",
                "short_name": "V1 Reviewer",
                "role_title": "Protocol reviewer",
                "tagline": "Explains the public Protocol.V1 wording clearly.",
            },
            tool_affinity={"preferred": ["library_read"], "can_request": []},
            risk_profile={"filesystem": "no_direct_write", "code_execution": "not_needed"},
        )
    )

    assert errors == []


@pytest.mark.parametrize(
    "public_name",
    [
        "Harness specialist",
        "Raw tools reviewer",
        "Raw logs reader",
    ],
)
def test_validates_public_profile_rejects_internal_runtime_terms(public_name: str) -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="public_profile_guard.v1",
            expert_profile={
                "public_name": public_name,
                "role_title": "Research specialist",
            },
            tool_affinity={"preferred": ["library_read"], "can_request": []},
            risk_profile={"filesystem": "no_direct_write", "code_execution": "not_needed"},
        )
    )

    assert any("expert_profile.public_name" in error for error in errors)


def test_validates_persona_prompt_rejects_internal_runtime_terms() -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="persona_guard.v1",
            persona_prompt=(
                _valid_persona_prompt()
                + "\nSafety Boundary:\nDo not expose harness refs or internal scheduling details.\n"
            ),
            tool_affinity={"preferred": ["library_read"], "can_request": []},
            risk_profile={"filesystem": "no_direct_write", "code_execution": "not_needed"},
        )
    )

    assert any("persona_prompt" in error for error in errors)


@pytest.mark.parametrize(
    "tool_name",
    [
        "sandbox.list_dir",
        "sandbox.glob",
        "sandbox.grep",
        "sandbox.read_file",
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.apply_patch",
        "sandbox.register_dataset",
        "sandbox.register_artifact",
        "sandbox.run_python",
        "sandbox.generate_figure",
    ],
)
def test_builtin_sandbox_tool_names_are_known_team_tools(tool_name: str) -> None:
    errors = validate_agent_template_contract(
        _template_with_valid_persona(
            id="sandbox_member.v1",
            tool_affinity={"preferred": [tool_name], "can_request": []},
            risk_profile={"filesystem": "sandbox_only", "code_execution": "required"},
        )
    )

    assert errors == []
