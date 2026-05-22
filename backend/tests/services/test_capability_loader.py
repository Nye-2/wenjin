"""Tests for CapabilityLoader — YAML seed loading."""

import textwrap
from unittest.mock import AsyncMock

import pytest


class _SeedCatalogFake:
    def __init__(self, *, has_capabilities: bool = False) -> None:
        self.has_catalog_capabilities = AsyncMock(return_value=has_capabilities)
        self.load_catalog_capability_seed_items = AsyncMock()
        self.list_catalog_capabilities = AsyncMock(return_value=[])


@pytest.mark.asyncio
async def test_load_seeds_when_empty(test_session, tmp_path):
    """Catalog empty → loads YAML through DataService."""
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

    dataservice = _SeedCatalogFake(has_capabilities=False)
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.items[0].data["display_name"] == "深度文献调研"
    assert command.items[0].data["intent_description"] == "用户希望对某个主题做学术性的深度文献调研"
    assert command.items[0].data["enabled"] is True
    assert command.items[0].data["trigger_phrases"] == []
    assert command.items[0].data["required_decisions"] == []


@pytest.mark.asyncio
async def test_load_skips_when_db_has_data(test_session, tmp_path):
    """Existing catalog data → loader returns 0."""

    from src.services.capability_loader import CapabilityLoader

    dataservice = _SeedCatalogFake(has_capabilities=True)
    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 0
    dataservice.load_catalog_capability_seed_items.assert_not_awaited()


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
        dataservice=_SeedCatalogFake(has_capabilities=False),
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

    dataservice = _SeedCatalogFake(has_capabilities=False)
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.items[0].data["ui_meta"] == {
        "icon": "search",
        "color": "purple",
        "order": 0,
        "stages": [{"id": "s1", "label": "第一步"}],
        "follow_up_prompt": "继续吧",
    }


@pytest.mark.asyncio
async def test_dataservice_branch_loads_seed_items(test_session, tmp_path):
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "test_cap.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        id: test_cap
        workspace_type: thesis
        display_name: Test
        intent_description: test intent
        brief_schema: {type: object}
        graph_template: {phases: []}
        ui_meta: {}
    """))

    from src.services.capability_loader import CapabilityLoader

    dataservice = AsyncMock()
    dataservice.has_catalog_capabilities.return_value = False
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        session=test_session,
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )

    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.seed_root == str(tmp_path / "capabilities")
    assert command.items[0].data["id"] == "test_cap"
    assert command.items[0].source_path == str(yaml_file)
