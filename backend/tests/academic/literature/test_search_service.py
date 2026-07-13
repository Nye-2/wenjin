"""Tests for literature projection over ToolOrchestrator receipts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.academic.literature.search_service import LiteratureSearchService
from src.tools.orchestrator import (
    ResearchToolOutcome,
    SourceReference,
    ToolCallerKind,
    ToolInvocationContext,
    ToolOutcomeStatus,
    ToolPolicy,
    VerificationStatus,
)


class _FakeOrchestrator:
    def __init__(self, outcome: ResearchToolOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    async def invoke(self, tool_id, arguments, *, context, policy):
        self.calls.append(
            {
                "tool_id": tool_id,
                "arguments": arguments,
                "context": context,
                "policy": policy,
            }
        )
        return self.outcome


def _context() -> ToolInvocationContext:
    return ToolInvocationContext(
        mission_id="mission-1",
        workspace_id="workspace-1",
        command_id="command-1",
        stage_id="literature",
        caller_id="workspace-agent",
        caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        lease_epoch=1,
        model_id="gpt-5.6-sol",
    )


def _policy() -> ToolPolicy:
    return ToolPolicy(
        policy_ref="mission-policy:1",
        allowed_tool_ids=("research.search_web",),
        granted_permissions=("external_research",),
        allowed_network_profiles=("model_provider_native_search",),
    )


def _outcome() -> ResearchToolOutcome:
    return ResearchToolOutcome(
        operation_id="op_1",
        operation_key="key_1",
        producer="workspace-agent",
        tool_id="research.search_web",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="One verified source returned.",
        source_refs=(
            SourceReference(
                source_id="web:paper-a",
                canonical_url="https://example.edu/paper-a",
                title="Paper A",
                authors=("Alice",),
                publisher="ACL",
                observed_at=datetime.now(UTC),
                supported_claim_refs=("resp:0-10",),
                verification_status=VerificationStatus.PROVIDER_RECEIPT,
            ),
        ),
        verification_status=VerificationStatus.PROVIDER_RECEIPT,
    )


@pytest.mark.asyncio
async def test_literature_search_projects_only_receipted_sources() -> None:
    orchestrator = _FakeOrchestrator(_outcome())
    service = LiteratureSearchService(
        orchestrator=orchestrator,  # type: ignore[arg-type]
        invocation_context=_context(),
        tool_policy=_policy(),
    )

    result = await service.search(
        query="  federated LoRA  ",
        discipline="Computer Science",
        limit=30,
    )

    assert orchestrator.calls[0]["tool_id"] == "research.search_web"
    assert orchestrator.calls[0]["arguments"] == {
        "query": "federated LoRA",
        "limit": 20,
    }
    assert result["retrieval"]["status"] == "ok"
    assert result["retrieval"]["verified"] == 1
    paper = result["verified_papers"][0]
    assert paper["source"] == "web_page"
    assert paper["evidence_level"] == "provider_search_receipt"
    assert paper["raw"]["producer_tool_id"] == "research.search_web"
    assert paper["raw"]["supported_claim_refs"] == ["resp:0-10"]


@pytest.mark.asyncio
async def test_literature_search_without_mission_tool_context_is_explicitly_partial() -> None:
    result = await LiteratureSearchService().search(query="agent planning")

    assert result["verified_papers"] == []
    assert result["retrieval"]["status"] == "partial"
    assert result["retrieval"]["tool_id"] == "research.search_web"
    assert result["retrieval"]["evidence_gaps"][0]["reason"] == (
        "mission_tool_context_required"
    )
