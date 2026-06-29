"""Tests for CapabilityLoader — YAML seed loading."""

import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _SeedCatalogFake:
    def __init__(self, *, has_capabilities: bool = False) -> None:
        self.has_catalog_capabilities = AsyncMock(return_value=has_capabilities)
        self.load_catalog_capability_seed_items = AsyncMock()
        self.list_catalog_capabilities = AsyncMock(return_value=[])


def _capability_v2_yaml(*, cap_id: str = "idea_to_thesis_manuscript") -> str:
    return textwrap.dedent(f"""\
        schema_version: capability.v2
        id: {cap_id}
        workspace_type: thesis
        enabled: true
        display:
          name: Idea 到论文全文
          description: 根据已确认 idea 生成或更新完整论文主稿
          icon: file-pen
          color: blue
          order: 10
          entry_tier: primary
        intent:
          description: 用户有明确研究 idea，希望生成或更新完整论文主稿
          trigger_phrases: [写全文]
        mission:
          goal: produce_or_update_primary_document
          primary_surface: prism
          document_role: primary_manuscript
          user_promise: 生成可审阅的主文档变更
          allowed_deliverables: [full_document_update]
        routing:
          when_to_use: [用户已有明确 research idea，需要生成或更新论文主稿]
          not_for: [概念解释, 单句润色, 期刊推荐]
          positive_examples:
            - 根据这个 idea 帮我写论文全文
            - 帮我把已有材料整理成论文主稿
            - 围绕这个研究问题生成 SCI 初稿
          negative_examples:
            - 这个概念是什么意思
            - 帮我把这句话润色一下
            - 这篇文章适合投什么期刊
          minimum_context:
            research_idea: required
          clarification:
            ask_when_missing:
              research_idea: 你的核心研究 idea 是什么？
        inputs:
          required_decisions: []
          brief_schema:
            type: object
            required: [research_idea]
            properties:
              research_idea: {{type: string}}
        context_policy:
          room_reads:
            library: summary
          prism_context:
            include_outline: true
          full_text_access: explicit_tool_only
        sandbox_policy:
          mode: conditional
          profiles: [analysis]
          allowed_operations: [run_python]
          isolation:
            provider: docker
            network: default_deny_allowlist
          resource_limits:
            cpu: 2
            memory_mb: 4096
          artifact_policy:
            review_required: true
        review_policy:
          default_targets: [prism_file_change]
          require_user_acceptance: true
          allow_bulk_accept: true
        quality_gates: [no_direct_primary_document_write]
        graph_template:
          phases:
            - name: drafting
              tasks:
                - name: write
                  subagent_type: react
                  skill_id: manuscript-writer
    """)


@pytest.mark.asyncio
async def test_load_seeds_when_empty(tmp_path):
    """Catalog empty → loads YAML through DataService."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "deep_research.yaml"
    yaml_file.write_text(_capability_v2_yaml(cap_id="deep_research"))

    from src.services.capability_loader import CapabilityLoader

    dataservice = _SeedCatalogFake(has_capabilities=False)
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.items[0].data["schema_version"] == "capability.v2"
    assert command.items[0].data["display_name"] == "Idea 到论文全文"
    assert command.items[0].data["intent_description"] == "用户有明确研究 idea，希望生成或更新完整论文主稿"
    assert command.items[0].data["enabled"] is True
    assert command.items[0].data["trigger_phrases"] == ["写全文"]
    assert command.items[0].data["required_decisions"] == []
    assert command.items[0].data["runtime"]["sandbox_policy"]["mode"] == "conditional"


@pytest.mark.asyncio
async def test_load_skips_when_db_has_data(tmp_path):
    """Existing catalog data → loader returns 0."""

    from src.services.capability_loader import CapabilityLoader

    dataservice = _SeedCatalogFake(has_capabilities=True)
    loader = CapabilityLoader(
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 0
    dataservice.load_catalog_capability_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_seed_updates_upserts_missing_and_changed_seed_owned_rows(tmp_path):
    """Existing catalog data → sync only missing or changed seed-owned capabilities."""
    seed_root = tmp_path / "capabilities"
    seed_dir = seed_root / "thesis"
    seed_dir.mkdir(parents=True)
    existing_yaml = seed_dir / "existing_seed.yaml"
    new_yaml = seed_dir / "new_seed.yaml"
    admin_yaml = seed_dir / "admin_custom.yaml"
    existing_yaml.write_text(_capability_v2_yaml(cap_id="existing_seed"))
    new_yaml.write_text(_capability_v2_yaml(cap_id="new_seed"))
    admin_yaml.write_text(_capability_v2_yaml(cap_id="admin_custom"))

    from src.services.capability_loader import CapabilityLoader

    dataservice = _SeedCatalogFake(has_capabilities=True)
    dataservice.list_catalog_capabilities.return_value = [
        SimpleNamespace(
            id="existing_seed",
            workspace_type="thesis",
            checksum="old-checksum",
            source_path=str(existing_yaml),
        ),
        SimpleNamespace(
            id="admin_custom",
            workspace_type="thesis",
            checksum="old-admin-checksum",
            source_path=None,
        ),
    ]
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 2
    loader = CapabilityLoader(seed_dir=seed_root, dataservice=dataservice)

    count = await loader.sync_seed_updates()

    assert count == 2
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.overwrite is False
    assert [item.data["id"] for item in command.items] == ["existing_seed", "new_seed"]


@pytest.mark.asyncio
async def test_load_validates_required_fields(tmp_path):
    """YAML missing required field → raises ValueError."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "incomplete.yaml"
    # Old workflow-era shape is no longer a valid runtime seed.
    yaml_file.write_text(textwrap.dedent("""\
        id: incomplete
        workspace_type: thesis
        display_name: Incomplete
        intent_description: Missing fields
    """))

    from src.services.capability_loader import CapabilityLoader

    loader = CapabilityLoader(
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=_SeedCatalogFake(has_capabilities=False),
    )

    with pytest.raises(ValueError, match="Invalid capability.v2 seed"):
        await loader.load_seeds_if_empty()


@pytest.mark.asyncio
async def test_loads_ui_meta_from_yaml(tmp_path):
    """YAML containing ui_meta is persisted verbatim onto the Capability row."""
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "test_cap.yaml"
    yaml_file.write_text(_capability_v2_yaml(cap_id="test_cap"))

    from src.services.capability_loader import CapabilityLoader

    dataservice = _SeedCatalogFake(has_capabilities=False)
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )
    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.items[0].data["ui_meta"] == {
        "icon": "file-pen",
        "color": "blue",
        "order": 10,
        "entry_tier": "primary",
        "stages": [],
    }


@pytest.mark.asyncio
async def test_dataservice_branch_loads_seed_items(tmp_path):
    seed_dir = tmp_path / "capabilities" / "thesis"
    seed_dir.mkdir(parents=True)
    yaml_file = seed_dir / "test_cap.yaml"
    yaml_file.write_text(_capability_v2_yaml(cap_id="test_cap"))

    from src.services.capability_loader import CapabilityLoader

    dataservice = AsyncMock()
    dataservice.has_catalog_capabilities.return_value = False
    dataservice.load_catalog_capability_seed_items.return_value.loaded = 1
    loader = CapabilityLoader(
        seed_dir=str(tmp_path / "capabilities"),
        dataservice=dataservice,
    )

    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_capability_seed_items.await_args.args[0]
    assert command.seed_root == str(tmp_path / "capabilities")
    assert command.items[0].data["id"] == "test_cap"
    assert command.items[0].source_path == str(yaml_file)
