"""Probe-evidence fixtures used only by model runtime tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.capability_profile import (
    CapabilityProbeCheck,
    CapabilityProfileAssessment,
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelTransportAPI,
    ModelTransportObservation,
    ProbeCheckStatus,
    SearchReceiptKind,
    WebSearchAPI,
    build_profile_from_probe,
    endpoint_fingerprint,
    native_search_endpoint_fingerprint,
)


def verified_capability_assessment(
    model_id: str = "gpt-5.6-sol",
    *,
    model_name: str | None = None,
    base_url: str = "https://api.nainai.love/v1",
    observed_at: datetime | None = None,
) -> CapabilityProfileAssessment:
    """Build deterministic test evidence; production can only use the live probe."""

    resolved_model_name = model_name or model_id
    observed = (observed_at or datetime.now(UTC)).astimezone(UTC)
    search_fingerprint = native_search_endpoint_fingerprint(base_url)
    passed_checks = (
        "structured_tool_calls",
        "strict_tool_arguments",
        "streaming_termination",
        "response_storage_disabled",
        "reasoning_effort:low",
        "reasoning_effort:medium",
        "reasoning_effort:high",
        "reasoning_effort:xhigh",
        "native_web_search_call",
        "search_source_citations",
    )
    evidence = ModelCapabilityProbeEvidence(
        model_id=model_id,
        model_name=resolved_model_name,
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name=resolved_model_name,
            base_url=base_url,
            generation_api=GenerationAPI.CHAT_COMPLETIONS,
        ),
        observed_at=observed,
        checks=(
            *(
                CapabilityProbeCheck(name=name, status=ProbeCheckStatus.PASSED)
                for name in passed_checks
            ),
            CapabilityProbeCheck(
                name="native_web_search_completed_event_boundary",
                status=ProbeCheckStatus.PASSED,
                detail_code=search_fingerprint,
            ),
        ),
        web_search_api=WebSearchAPI.RESPONSES_WEB_SEARCH,
        search_receipts=(
            SearchReceiptKind.WEB_SEARCH_CALL,
            SearchReceiptKind.ANNOTATIONS_SOURCES,
        ),
        transport_observations=(
            ModelTransportObservation(
                transport_api=ModelTransportAPI.CHAT_COMPLETIONS,
                protocol_conformance=True,
                detail_code="clean_done_and_close",
            ),
            ModelTransportObservation(
                transport_api=ModelTransportAPI.RESPONSES,
                protocol_conformance=True,
                detail_code=search_fingerprint,
            ),
        ),
    )
    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


__all__ = ["verified_capability_assessment"]
