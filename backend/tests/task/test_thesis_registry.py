"""Tests for thesis workspace capability data in the capabilities table."""

import pytest
from sqlalchemy import select

from src.database.models.capability import Capability
from src.database import get_db_session


@pytest.mark.asyncio
async def test_thesis_has_core_capabilities():
    async with get_db_session() as db:
        result = await db.execute(
            select(Capability).where(
                Capability.workspace_type == "thesis",
                Capability.enabled == True,  # noqa: E712
            )
        )
        ids = sorted(c.id for c in result.scalars().all())
    expected = [
        "deep_research",
        "figure_generation",
        "literature_management",
        "opening_research",
        "outline_generate",
        "section_revise",
        "section_write",
    ]
    assert ids == expected


@pytest.mark.asyncio
async def test_thesis_capability_fields_populated():
    async with get_db_session() as db:
        result = await db.execute(
            select(Capability).where(
                Capability.workspace_type == "thesis",
                Capability.id == "deep_research",
            )
        )
        cap = result.scalars().first()
    assert cap is not None
    assert cap.display_name
    assert cap.description
