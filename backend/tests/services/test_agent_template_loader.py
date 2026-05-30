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


@pytest.mark.asyncio
async def test_loads_agent_template_seeds_through_dataservice(test_session, tmp_path) -> None:
    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir()
    seed_file = seed_dir / "research_scout.yaml"
    seed_file.write_text(_agent_template_yaml(), encoding="utf-8")

    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = False
    dataservice.load_agent_template_seed_items.return_value.loaded = 1
    loader = AgentTemplateLoader(
        test_session,
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
async def test_skips_agent_template_seed_when_catalog_has_data(test_session, tmp_path) -> None:
    from src.services.agent_template_loader import AgentTemplateLoader

    dataservice = AsyncMock()
    dataservice.has_agent_templates.return_value = True
    loader = AgentTemplateLoader(
        test_session,
        seed_dir=tmp_path / "agent_templates",
        dataservice=dataservice,
    )

    count = await loader.load_seeds_if_empty()

    assert count == 0
    dataservice.load_agent_template_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_template_loader_validates_required_shape(test_session, tmp_path) -> None:
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
        test_session,
        seed_dir=seed_dir,
        dataservice=dataservice,
    )

    with pytest.raises(ValueError, match="display_role is required"):
        await loader.load_seeds_if_empty()
