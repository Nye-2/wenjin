"""Round-trip tests for capabilities and capability_active_versions tables."""

import pytest
from sqlalchemy import select

from tests.database.conftest import DbCapability, DbCapabilityActiveVersion


@pytest.mark.asyncio
async def test_capability_create_and_query(test_session):
    """Insert a Capability, query by (id, workspace_type, version), verify round-trip."""
    cap = DbCapability(
        id="deep_research",
        workspace_type="thesis",
        version=1,
        display_name="深度文献调研",
        enabled=True,
        intent_description="用户希望对某个主题做学术性的深度文献调研",
        trigger_phrases=["调研一下", "找综述"],
        required_decisions=[{"key": "topic_scope", "ask": "主题边界是？", "type": "string"}],
        brief_schema={"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}},
        graph_template={"phases": [{"name": "discover", "tasks": [{"name": "search", "subagent_type": "scholar_searcher"}]}]},
        system_prompt="你是学术文献调研专家。",
        result_card_template="literature_review",
    )
    test_session.add(cap)
    await test_session.commit()

    result = (
        await test_session.execute(
            select(DbCapability).where(
                DbCapability.id == "deep_research",
                DbCapability.workspace_type == "thesis",
                DbCapability.version == 1,
            )
        )
    ).scalar_one()

    assert result.id == "deep_research"
    assert result.workspace_type == "thesis"
    assert result.version == 1
    assert result.display_name == "深度文献调研"
    assert result.enabled is True
    assert result.trigger_phrases == ["调研一下", "找综述"]
    assert result.brief_schema == {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}}
    assert result.graph_template["phases"][0]["name"] == "discover"
    assert result.system_prompt == "你是学术文献调研专家。"
    assert result.result_card_template == "literature_review"


@pytest.mark.asyncio
async def test_active_version_create(test_session):
    """Insert Capability + CapabilityActiveVersion, verify join works."""
    cap = DbCapability(
        id="deep_research",
        workspace_type="thesis",
        version=1,
        display_name="深度文献调研",
        enabled=True,
        intent_description="用户希望对某个主题做学术性的深度文献调研",
        brief_schema={"type": "object"},
        graph_template={"phases": []},
        system_prompt="你是学术文献调研专家。",
        result_card_template="literature_review",
    )
    test_session.add(cap)
    await test_session.flush()

    active = DbCapabilityActiveVersion(
        id="deep_research",
        workspace_type="thesis",
        active_version=1,
    )
    test_session.add(active)
    await test_session.commit()

    # Verify the active version record
    result = (
        await test_session.execute(
            select(DbCapabilityActiveVersion).where(
                DbCapabilityActiveVersion.id == "deep_research",
                DbCapabilityActiveVersion.workspace_type == "thesis",
            )
        )
    ).scalar_one()
    assert result.active_version == 1

    # Verify join: capability where version matches active_version
    joined = (
        await test_session.execute(
            select(DbCapability)
            .join(
                DbCapabilityActiveVersion,
                (DbCapability.id == DbCapabilityActiveVersion.id)
                & (DbCapability.workspace_type == DbCapabilityActiveVersion.workspace_type)
                & (DbCapability.version == DbCapabilityActiveVersion.active_version),
            )
            .where(DbCapabilityActiveVersion.id == "deep_research")
        )
    ).scalar_one()
    assert joined.id == "deep_research"
    assert joined.version == 1
    assert joined.display_name == "深度文献调研"
