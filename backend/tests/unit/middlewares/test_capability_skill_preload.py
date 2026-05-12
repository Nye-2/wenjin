"""Tests for CapabilitySkillPreloadMiddleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.middlewares.capability_skill_preload import (
    CapabilitySkillPreloadMiddleware,
)
from src.agents.thread_state import ThreadState, create_thread_state


def _cap(**kw):
    base = dict(
        id="deep_research",
        display_name="深度调研",
        description="desc",
        intent_description="intent",
        trigger_phrases=["调研"],
        enabled=True,
        workspace_type="thesis",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _skill(**kw):
    base = dict(
        id="scholar-searcher",
        display_name="Scholar Searcher",
        description="searcher skill",
        subagent_type="searcher",
        enabled=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestCapabilitySkillPreload:
    @pytest.mark.asyncio
    async def test_skips_when_no_workspace_type(self):
        mw = CapabilitySkillPreloadMiddleware()
        state = create_thread_state({"messages": []})

        update = await mw.before_model(state, {})

        assert update == {}

    @pytest.mark.asyncio
    async def test_populates_state_from_db(self):
        mw = CapabilitySkillPreloadMiddleware()
        state = create_thread_state({"messages": [], "workspace_type": "thesis"})

        with patch.object(
            CapabilitySkillPreloadMiddleware,
            "_fetch",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "deep_research",
                            "display_name": "深度调研",
                            "description": "desc",
                            "intent_description": "intent",
                            "trigger_phrases": ["调研"],
                        }
                    ],
                    [
                        {
                            "id": "scholar-searcher",
                            "display_name": "Scholar Searcher",
                            "description": "searcher skill",
                            "subagent_type": "searcher",
                        }
                    ],
                )
            ),
        ):
            update = await mw.before_model(state, {})

        assert update["available_capabilities"][0]["id"] == "deep_research"
        assert update["available_skills"][0]["subagent_type"] == "searcher"

    @pytest.mark.asyncio
    async def test_swallows_db_errors(self):
        """A DB error must not crash the chat turn — leave state untouched."""
        mw = CapabilitySkillPreloadMiddleware()
        state: ThreadState = create_thread_state(
            {"messages": [], "workspace_type": "sci"}
        )

        with patch.object(
            CapabilitySkillPreloadMiddleware,
            "_fetch",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            update = await mw.before_model(state, {})

        assert update == {}

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self):
        """Timeout must not crash the chat turn."""
        mw = CapabilitySkillPreloadMiddleware(timeout=0.01)
        state = create_thread_state(
            {"messages": [], "workspace_type": "sci"}
        )

        async def slow(*a, **kw):
            import asyncio

            await asyncio.sleep(1.0)
            return ([], [])

        with patch.object(CapabilitySkillPreloadMiddleware, "_fetch", new=slow):
            update = await mw.before_model(state, {})

        assert update == {}
