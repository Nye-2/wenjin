"""Mission catalog readiness is strict about policy coverage and native search."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.gateway import health


class FakeClient:
    def __init__(self, *, policies, skills) -> None:
        self.policies = policies
        self.skills = skills

    async def list_mission_policies(self, *, enabled_only: bool):
        assert enabled_only is True
        return self.policies

    async def list_worker_skills(self, *, enabled_only: bool):
        assert enabled_only is True
        return self.skills


def policy(workspace_type: str, *, search: bool = False):
    groups = ("model_native_web_search",) if search else ("workspace_read",)
    return SimpleNamespace(
        id=f"{workspace_type}-policy",
        workspace_type=workspace_type,
        to_contract=lambda: SimpleNamespace(
            allowed_worker_skills=("skill-1",),
            tool_policy=SimpleNamespace(allowed_tool_groups=groups),
        ),
    )


def install_client(monkeypatch, *, policies, skills) -> None:
    @asynccontextmanager
    async def provider():
        yield FakeClient(policies=policies, skills=skills)

    monkeypatch.setattr(health, "dataservice_client", provider)


@pytest.mark.asyncio
async def test_readiness_requires_every_workspace_policy(monkeypatch) -> None:
    install_client(
        monkeypatch,
        policies=[policy("sci")],
        skills=[SimpleNamespace(id="skill-1")],
    )

    report = await health.check_mission_catalog()

    assert report["status"] == "unhealthy"
    assert "thesis" in report["missing_workspace_types"]


@pytest.mark.asyncio
async def test_readiness_rejects_enabled_policy_with_unverified_search(
    monkeypatch,
) -> None:
    workspace_types = (
        "sci",
        "thesis",
        "proposal",
        "software_copyright",
        "math_modeling",
        "patent",
    )
    install_client(
        monkeypatch,
        policies=[policy(item, search=item == "sci") for item in workspace_types],
        skills=[SimpleNamespace(id="skill-1")],
    )
    monkeypatch.setattr(
        health,
        "get_default_runtime_model_id",
        lambda: "gpt-5.6-sol",
    )
    monkeypatch.setattr(
        health,
        "get_runtime_model_config",
        lambda _model_id: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "src.services.mission_catalog_readiness.native_search_capability",
        lambda _model: SimpleNamespace(available=False, reason_codes=("missing_receipts",)),
    )

    report = await health.check_mission_catalog()

    assert report["status"] == "unhealthy"
    assert report["search_policy_ids"] == ["sci-policy"]
    assert report["reason_codes"] == ["missing_receipts"]
