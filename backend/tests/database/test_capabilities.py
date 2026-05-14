"""Round-trip tests for capabilities and capability_skills tables."""

import pytest
from sqlalchemy import select

from tests.database.conftest import DbCapability, DbCapabilitySkill


@pytest.mark.asyncio
async def test_capability_create_and_query(test_session):
    cap = DbCapability(
        id="deep_research",
        workspace_type="thesis",
        display_name="深度文献调研",
        enabled=True,
        description="围绕主题做系统化文献检索",
        intent_description="用户希望对某个主题做学术性的深度文献调研",
        trigger_phrases=["调研一下", "找综述"],
        required_decisions=[{"key": "topic_scope", "ask": "主题边界是？", "type": "string"}],
        brief_schema={"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}},
        graph_template={"phases": [{"name": "discover", "tasks": [{"name": "search", "subagent_type": "searcher", "skill_id": "scholar-searcher"}]}]},
        ui_meta={"icon": "search", "color": "purple", "order": 0},
    )
    test_session.add(cap)
    await test_session.commit()

    result = (
        await test_session.execute(
            select(DbCapability).where(
                DbCapability.id == "deep_research",
                DbCapability.workspace_type == "thesis",
            )
        )
    ).scalar_one()

    assert result.id == "deep_research"
    assert result.workspace_type == "thesis"
    assert result.display_name == "深度文献调研"
    assert result.enabled is True
    assert result.trigger_phrases == ["调研一下", "找综述"]
    assert result.graph_template["phases"][0]["name"] == "discover"
    assert result.ui_meta == {"icon": "search", "color": "purple", "order": 0}


@pytest.mark.asyncio
async def test_capability_skill_create_and_query(test_session):
    skill = DbCapabilitySkill(
        id="scholar-searcher",
        display_name="学术文献检索员",
        description="调 Semantic Scholar",
        subagent_type="searcher",
        prompt="(unused)",
        allowed_tools=[],
        resources=[],
        config={"sources": ["semantic_scholar"]},
    )
    test_session.add(skill)
    await test_session.commit()

    result = (
        await test_session.execute(
            select(DbCapabilitySkill).where(DbCapabilitySkill.id == "scholar-searcher")
        )
    ).scalar_one()

    assert result.id == "scholar-searcher"
    assert result.subagent_type == "searcher"
    assert result.config == {"sources": ["semantic_scholar"]}
    assert result.enabled is True
