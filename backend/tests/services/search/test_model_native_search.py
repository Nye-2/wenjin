from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.capability_profile import (
    CapabilityProbeCheck,
    GenerationAPI,
    GenerationTransportObservation,
    ModelCapabilityProbeEvidence,
    ProbeCheckStatus,
    SearchReceiptKind,
    WebSearchAPI,
    build_profile_from_probe,
    endpoint_fingerprint,
    native_search_endpoint_fingerprint,
    unverified_capability_assessment,
)
from src.services.model_catalog_cache import RuntimeModelConfig
from src.services.search.model_native import (
    ModelNativeSearchHandler,
    ModelNativeSearchInput,
    NativeSearchReceiptError,
    parse_native_search_receipt,
)
from src.tools.orchestrator import ToolOperation, ToolOutcomeStatus


def _provider_response() -> dict:
    return {
        "id": "resp_123",
        "status": "completed",
        "output": [
            {
                "id": "ws_123",
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": "federated LoRA",
                    "sources": [
                        {
                            "url": "https://example.edu/paper",
                            "title": "Federated LoRA",
                        }
                    ],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Federated LoRA is studied.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.edu/paper",
                                "title": "Federated LoRA",
                                "start_index": 0,
                                "end_index": 14,
                            }
                        ],
                    }
                ],
            },
        ],
    }


def _operation() -> ToolOperation:
    return ToolOperation(
        mission_id="mission-1",
        operation_id="op_1",
        operation_key="key-1",
        command_id="command-1",
        stage_id="stage-1",
        caller_id="agent-1",
        caller_kind="workspace_agent",
        model_id="gpt-5.6-sol",
        tool_id="research.search_web",
        tool_version="1.0.0",
        descriptor_schema_hash="b" * 64,
        args_hash="a" * 64,
        policy_snapshot_ref="policy:1",
        lease_epoch=1,
        attempt=1,
    )


def _runtime(assessment) -> RuntimeModelConfig:
    return RuntimeModelConfig(
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        category="llm",
        provider="OpenAI",
        model="gpt-5.6-sol",
        api_key="sk-test",
        base_url="https://api.nainai.love/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        max_tokens=128000,
        temperature=0.3,
        timeout_seconds=30,
        max_retries=0,
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
        default_headers={},
        pricing_policy_id="model-standard",
        is_default=True,
        config_version=1,
    )


def test_native_search_parser_requires_call_and_citation_receipts() -> None:
    receipt = parse_native_search_receipt(_provider_response())

    assert receipt.search_call_ids == ("ws_123",)
    assert receipt.sources[0].url == "https://example.edu/paper"
    assert receipt.citations[0].title == "Federated LoRA"


@pytest.mark.parametrize(
    "response",
    [
        {"choices": [{"message": {"content": "https://example.edu/paper"}}]},
        {"id": "resp", "status": "completed", "output": []},
        {
            "id": "resp",
            "status": "completed",
            "output": [
                {
                    "id": "ws",
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {"sources": []},
                }
            ],
        },
    ],
)
def test_native_search_parser_rejects_prose_or_incomplete_receipts(response: dict) -> None:
    with pytest.raises(NativeSearchReceiptError):
        parse_native_search_receipt(response)


@pytest.mark.asyncio
async def test_unverified_profile_returns_gap_before_executor_dispatch() -> None:
    executor_called = False

    async def executor(**_kwargs):
        nonlocal executor_called
        executor_called = True
        return _provider_response()

    runtime = _runtime(
        unverified_capability_assessment(
            model_id="gpt-5.6-sol",
            model_name="gpt-5.6-sol",
            base_url="https://api.nainai.love/v1",
            generation_api=GenerationAPI.CHAT_COMPLETIONS,
        )
    )
    handler = ModelNativeSearchHandler(
        executor=executor,
        model_resolver=lambda _model_id: runtime,
    )

    result = await handler(
        _operation(),
        ModelNativeSearchInput(query="federated LoRA"),
    )

    assert result.status is ToolOutcomeStatus.PARTIAL
    assert result.evidence_refs[0].metadata["reason"] == "capability_unverified"
    assert "completed_event_boundary_not_verified" in result.evidence_refs[0].metadata["reason_codes"]
    assert executor_called is False


def _search_capable_assessment():
    observed_at = datetime.now(UTC)
    evidence = ModelCapabilityProbeEvidence(
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name="gpt-5.6-sol",
            base_url="https://api.nainai.love/v1",
            generation_api=GenerationAPI.CHAT_COMPLETIONS,
        ),
        observed_at=observed_at,
        checks=(
            CapabilityProbeCheck(name="native_web_search_call", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="search_source_citations", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(
                name="native_web_search_completed_event_boundary",
                status=ProbeCheckStatus.PASSED,
                detail_code=native_search_endpoint_fingerprint(
                    "https://api.nainai.love/v1"
                ),
            ),
        ),
        web_search_api=WebSearchAPI.RESPONSES_WEB_SEARCH,
        search_receipts=(
            SearchReceiptKind.WEB_SEARCH_CALL,
            SearchReceiptKind.ANNOTATIONS_SOURCES,
        ),
        transport_observations=(
            GenerationTransportObservation(
                generation_api=GenerationAPI.CHAT_COMPLETIONS,
                protocol_conformance=True,
            ),
            GenerationTransportObservation(
                generation_api=GenerationAPI.RESPONSES,
                protocol_conformance=True,
            ),
        ),
    )
    from src.models.capability_profile import CapabilityProfileAssessment

    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


@pytest.mark.asyncio
async def test_search_capable_profile_materializes_only_receipted_sources() -> None:
    runtime = _runtime(_search_capable_assessment())

    async def executor(**_kwargs):
        return _provider_response()

    result = await ModelNativeSearchHandler(
        executor=executor,
        model_resolver=lambda _model_id: runtime,
    )(
        _operation(),
        ModelNativeSearchInput(query="federated LoRA"),
    )

    assert result.status is ToolOutcomeStatus.SUCCESS
    assert result.evidence_refs[0].kind == "provider_search_receipt"
    assert result.evidence_refs[0].metadata["search_call_ids"] == ["ws_123"]
    assert result.source_refs[0].canonical_url == "https://example.edu/paper"
    assert result.source_refs[0].verification_status.value == "provider_receipt"
