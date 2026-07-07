"""Tests for AgentTemplateLoader — DataService-backed team template seeding."""

from __future__ import annotations

import textwrap
from types import SimpleNamespace
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
        persona_prompt: |-
          You are a research specialist supporting academic work.

          Role Boundary:
          Stay within literature discovery, source triage, and evidence synthesis.

          Evidence Rules:
          Ground claims in cited sources and flag uncertainty clearly.
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
async def test_agent_template_rejects_public_internal_ids(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(
        _agent_template_yaml()
        + textwrap.dedent("""\
            expert_profile:
              public_name: research_scout.v1
              role_title: Tool log operator
              avatar_label: 文
              tone: witty_professional
              status_phrases:
                running: Reading sources
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

    with pytest.raises(ValueError, match="public_name|internal terminology"):
        await loader.load_seeds_if_empty()
    dataservice.load_agent_template_seed_items.assert_not_awaited()


@pytest.mark.parametrize(
    ("profile_yaml", "match"),
    [
        (
            """\
              public_name: 文献猎手 Nora
              short_name: bad_template.v1
              role_title: 文献检索专家
              avatar_label: 文
              tone: witty_professional
              status_phrases:
                running: Reading sources
            """,
            "short_name|internal terminology",
        ),
        (
            """\
              public_name: 文献猎手 Nora
              short_name: 文献猎手
              role_title: 文献检索专家
              avatar_label: 文
              tone: witty_professional
              tagline: Check stdout before writing.
              status_phrases:
                running: Reading sources
            """,
            "tagline|stdout|internal terminology",
        ),
        (
            """\
              public_name: 文献猎手 Nora
              short_name: 文献猎手
              role_title: 文献检索专家
              avatar_label: 文
              tone: witty_professional
              status_phrases:
                running: Checking stderr
            """,
            "status_phrases.running|stderr|internal terminology",
        ),
    ],
)
@pytest.mark.asyncio
async def test_agent_template_rejects_internal_terms_in_public_profile_fields(
    tmp_path,
    profile_yaml: str,
    match: str,
) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(
        _agent_template_yaml()
        + "expert_profile:\n"
        + textwrap.indent(textwrap.dedent(profile_yaml), "  "),
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

    with pytest.raises(ValueError, match=match):
        await loader.load_seeds_if_empty()
    dataservice.load_agent_template_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_template_rejects_persona_without_role_boundary(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(
        _agent_template_yaml().replace(
            textwrap.dedent("""\
                persona_prompt: |-
                  You are a research specialist supporting academic work.

                  Role Boundary:
                  Stay within literature discovery, source triage, and evidence synthesis.

                  Evidence Rules:
                  Ground claims in cited sources and flag uncertainty clearly.
            """),
            "persona_prompt: You are a helper.\n",
        ),
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

    with pytest.raises(ValueError, match="Role Boundary"):
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
async def test_sync_seed_updates_upserts_missing_and_changed_seed_owned_rows(tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    existing_seed = seed_dir / "existing_seed.yaml"
    new_seed = seed_dir / "new_seed.yaml"
    admin_custom = seed_dir / "admin_custom.yaml"
    existing_seed.write_text(
        _agent_template_yaml().replace("research_scout.v1", "existing_seed.v1"),
        encoding="utf-8",
    )
    new_seed.write_text(
        _agent_template_yaml().replace("research_scout.v1", "new_seed.v1"),
        encoding="utf-8",
    )
    admin_custom.write_text(
        _agent_template_yaml().replace("research_scout.v1", "admin_custom.v1"),
        encoding="utf-8",
    )

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.list_agent_templates.return_value = [
        SimpleNamespace(
            id="existing_seed.v1",
            checksum="old-checksum",
            source_path=str(existing_seed),
        ),
        SimpleNamespace(
            id="admin_custom.v1",
            checksum="old-admin-checksum",
            source_path=None,
        ),
    ]
    dataservice.load_agent_template_seed_items.return_value = SimpleNamespace(loaded=2)
    loader = AgentTemplateLoader(
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    count = await loader.sync_seed_updates()

    assert count == 2
    command = dataservice.load_agent_template_seed_items.await_args.args[0]
    assert command.overwrite is False
    assert [item.data["id"] for item in command.items] == [
        "existing_seed.v1",
        "new_seed.v1",
    ]


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
            persona_prompt: |-
              You are an experiment role supporting reproducible evidence work.

              Role Boundary:
              Stay within reproducible analysis planning and evidence checks.

              Evidence Rules:
              Report commands, inputs, and limitations needed to reproduce results.
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
