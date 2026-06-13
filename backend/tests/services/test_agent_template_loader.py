"""Tests for AgentTemplateLoader — DataService-backed team template seeding."""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock

import pytest


def _agent_template_yaml() -> str:
    return textwrap.dedent("""\
        schema_version: agent_template.v1
        id: research_scout.v1
        enabled: true
        display_role: 文献检索员
        category: research
        description: 检索、筛选、归纳文献。
        persona_prompt: You are a research specialist.
        default_skills:
        - research-scout
        tool_affinity:
          preferred:
          - web_search
          can_request:
          - library_read
        risk_profile:
          room_write: staged_only
        output_contracts:
        - literature_evidence_report.v1
        quality_expectations:
        - claims map to sources
        runtime_defaults:
          max_turns: 8
    """)


def _agent_template_yaml_with_expert_profile() -> str:
    return _agent_template_yaml() + textwrap.dedent("""\
        expert_profile:
          public_name: 文献猎手 Nora
          role_title: 文献检索专家
          avatar_label: 文
          tone: witty_professional
          status_phrases:
            running: 扫文献雷达中
    """)


@pytest.mark.asyncio
async def test_loads_agent_template_seeds_through_dataservice(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(_agent_template_yaml(), encoding="utf-8")

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    dataservice.load_agent_template_seed_items.return_value.loaded = 1
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_agent_template_seed_items.await_args.args[0]
    assert command.seed_root == str(seed_dir)
    assert command.items[0].source_path == str(seed_file)
    assert command.items[0].data["id"] == "research_scout.v1"
    assert command.items[0].data["display_role"] == "文献检索员"


@pytest.mark.asyncio
async def test_agent_template_loader_preserves_valid_expert_profile(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(_agent_template_yaml_with_expert_profile(), encoding="utf-8")

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    dataservice.load_agent_template_seed_items.return_value.loaded = 1
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    await loader.load_seeds_if_empty()

    command = dataservice.load_agent_template_seed_items.await_args.args[0]
    profile = command.items[0].data["expert_profile"]
    assert profile["schema_version"] == "wenjin.team.expert_profile.v1"
    assert profile["public_name"] == "文献猎手 Nora"
    assert profile["status_phrases"]["running"] == "扫文献雷达中"


@pytest.mark.asyncio
async def test_agent_template_loader_rejects_invalid_expert_profile(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(
        _agent_template_yaml()
        + textwrap.dedent("""\
            expert_profile:
              public_name: 文献猎手 Nora
              role_title: 文献检索专家
              status_phrases:
                sleeping: zzz
        """),
        encoding="utf-8",
    )

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    dataservice.load_agent_template_seed_items.return_value.loaded = 1
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    with pytest.raises(ValueError, match="expert_profile"):
        await loader.load_seeds_if_empty()
    dataservice.load_agent_template_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_agent_template_seed_when_catalog_has_data(tmp_path) -> None:
    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = True
    loader = AgentTemplateLoader(
        seed_dir=tmp_path / "agent_templates",
        dataservice=dataservice,
    )

    count = await loader.load_seeds_if_empty()

    assert count == 0
    dataservice.load_agent_template_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_template_loader_validates_required_shape(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    (seed_dir / "broken.yaml").write_text(
        "schema_version: agent_template.v1\nid: broken.v1\n",
        encoding="utf-8",
    )

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    with pytest.raises(ValueError, match="display_role is required"):
        await loader.load_seeds_if_empty()


@pytest.mark.asyncio
async def test_agent_template_loader_rejects_invalid_harness_tool_contract(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    (seed_dir / "bad_sandbox_agent.yaml").write_text(
        textwrap.dedent("""\
            schema_version: agent_template.v1
            id: bad_sandbox_agent.v1
            enabled: true
            display_role: 坏实验员
            category: evidence
            description: Bad sandbox role.
            persona_prompt: You are an experiment role.
            default_skills:
            - evidence-analyst
            tool_affinity:
              preferred:
              - sandbox_python
              can_request:
              - sandbox.run_command
            risk_profile:
              filesystem: no_direct_write
              code_execution: not_needed
              room_write: staged_only
            output_contracts:
            - reproducible_evidence_report.v1
            quality_expectations:
            - evidence is reproducible
            runtime_defaults:
              max_turns: 8
        """),
        encoding="utf-8",
    )

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    with pytest.raises(ValueError, match="retired harness tool 'sandbox_python'"):
        await loader.load_seeds_if_empty()
    dataservice.load_agent_template_seed_items.assert_not_awaited()
