"""Tests for CapabilityLoader — YAML seed loading."""

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.database.conftest import DbCapability


@pytest.mark.asyncio
async def test_load_seeds_when_empty(test_session, tmp_path):
    """DB empty → loads YAML → Capability exists."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "deep_research.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        id: deep_research
        workspace_type: thesis
        display_name: 深度文献调研
        description: 围绕主题做系统化文献检索
        intent_description: 用户希望对某个主题做学术性的深度文献调研
        brief_schema:
          type: object
          required: [topic]
          properties:
            topic: {type: string}
        graph_template:
          phases:
            - name: discover
              tasks:
                - name: search
                  subagent_type: searcher
        ui_meta:
          icon: search
          color: purple
          order: 0
    """))

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        model=DbCapability,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1

    result = (
        await test_session.execute(
            select(DbCapability).where(
                DbCapability.id == "deep_research",
                DbCapability.workspace_type == "thesis",
            )
        )
    ).scalar_one()

    assert result.display_name == "深度文献调研"
    assert result.intent_description == "用户希望对某个主题做学术性的深度文献调研"
    assert result.enabled is True
    assert result.trigger_phrases == []
    assert result.required_decisions == []


@pytest.mark.asyncio
async def test_load_skips_when_db_has_data(test_session, tmp_path):
    """Pre-insert a Capability → loader returns 0."""
    cap = DbCapability(
        id="existing",
        workspace_type="thesis",
        display_name="Existing",
        description="test",
        intent_description="test",
        brief_schema={"type": "object"},
        graph_template={"phases": []},
        ui_meta={},
    )
    test_session.add(cap)
    await test_session.commit()

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        model=DbCapability,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 0


@pytest.mark.asyncio
async def test_load_validates_required_fields(test_session, tmp_path):
    """YAML missing required field → raises ValueError."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "incomplete.yaml"
    # Missing 'brief_schema', 'graph_template', and 'ui_meta'
    yaml_file.write_text(textwrap.dedent("""\
        id: incomplete
        workspace_type: thesis
        display_name: Incomplete
        intent_description: Missing fields
    """))

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        model=DbCapability,
    )

    with pytest.raises(ValueError, match="Missing required fields"):
        await loader.load_seeds_if_empty()


@pytest.mark.asyncio
async def test_loads_ui_meta_from_yaml(test_session, tmp_path):
    """YAML containing ui_meta is persisted verbatim onto the Capability row."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "test_cap.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        id: test_cap
        workspace_type: thesis
        display_name: 测试
        intent_description: test intent
        brief_schema: {type: object}
        graph_template: {phases: []}
        ui_meta:
          icon: search
          color: purple
          order: 0
          stages:
            - {id: s1, label: 第一步}
          follow_up_prompt: 继续吧
    """))

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        model=DbCapability,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1

    result = (
        await test_session.execute(
            select(DbCapability).where(
                DbCapability.id == "test_cap",
                DbCapability.workspace_type == "thesis",
            )
        )
    ).scalar_one()

    assert result.ui_meta == {
        "icon": "search",
        "color": "purple",
        "order": 0,
        "stages": [{"id": "s1", "label": "第一步"}],
        "follow_up_prompt": "继续吧",
    }
