"""Versioned, probe-backed model capability contracts.

The model catalog stores these objects as JSON. Runtime code must derive
capabilities from probe evidence rather than from provider names or mutable
``supports_*`` switches.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal, Self
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.reasoning import ReasoningEffort

PROFILE_VERSION = "wenjin.model-capability-profile.v1"
PROBE_VERSION = "wenjin.model-capability-probe.v1"


class GenerationAPI(StrEnum):
    """Wire API used for language-model generation."""

    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"


class WebSearchAPI(StrEnum):
    RESPONSES_WEB_SEARCH = "responses_web_search"
    NONE = "none"


class SearchReceiptKind(StrEnum):
    WEB_SEARCH_CALL = "web_search_call"
    ANNOTATIONS_SOURCES = "annotations_sources"


class ProbeCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CapabilityProbeCheck(BaseModel):
    """One harmless capability observation without provider payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    status: ProbeCheckStatus
    detail_code: str | None = Field(default=None, max_length=160)


class GenerationTransportObservation(BaseModel):
    """Protocol completion result for one generation API surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generation_api: GenerationAPI
    protocol_conformance: bool
    detail_code: str | None = Field(default=None, max_length=160)


class ModelCapabilityProbeEvidence(BaseModel):
    """Redacted evidence recorded by an explicit capability probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    probe_version: Literal[PROBE_VERSION] = PROBE_VERSION
    model_id: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=200)
    generation_api: GenerationAPI | None
    endpoint_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    checks: tuple[CapabilityProbeCheck, ...] = ()
    web_search_api: WebSearchAPI = WebSearchAPI.NONE
    search_receipts: tuple[SearchReceiptKind, ...] = ()
    transport_observations: tuple[GenerationTransportObservation, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def _observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_unique_evidence(self) -> Self:
        check_names = [check.name for check in self.checks]
        if len(check_names) != len(set(check_names)):
            raise ValueError("probe check names must be unique")
        apis = [item.generation_api for item in self.transport_observations]
        if len(apis) != len(set(apis)):
            raise ValueError("transport observations must be unique per generation API")
        if self.web_search_api is WebSearchAPI.NONE and self.search_receipts:
            raise ValueError("search receipts require a web search API")
        return self

    def check_passed(self, name: str) -> bool:
        return any(check.name == name and check.status is ProbeCheckStatus.PASSED for check in self.checks)

    def transport_conforms(self, generation_api: GenerationAPI) -> bool:
        return any(
            item.generation_api is generation_api and item.protocol_conformance
            for item in self.transport_observations
        )

    def evidence_hash(self) -> str:
        return _canonical_hash(self.model_dump(mode="json"))


class ModelCapabilityProfile(BaseModel):
    """Runtime capability truth derived from one probe evidence object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_version: Literal[PROFILE_VERSION] = PROFILE_VERSION
    model_id: str = Field(min_length=1, max_length=100)
    generation_api: GenerationAPI | None
    structured_tool_calls: bool = False
    strict_tool_arguments: bool = False
    streaming: bool = False
    reasoning_efforts: tuple[ReasoningEffort, ...] = ()
    native_web_search: bool = False
    web_search_api: WebSearchAPI = WebSearchAPI.NONE
    search_receipts: tuple[SearchReceiptKind, ...] = ()
    structured_outputs: bool = False
    vision: bool = False
    response_storage_disabled: bool = False
    protocol_conformance: bool = False
    transport_observations: tuple[GenerationTransportObservation, ...] = ()
    observed_at: datetime
    probe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("observed_at")
    @classmethod
    def _profile_observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_capability_dependencies(self) -> Self:
        if self.strict_tool_arguments and not self.structured_tool_calls:
            raise ValueError("strict tool arguments require structured tool calls")
        if self.native_web_search:
            if self.web_search_api is WebSearchAPI.NONE:
                raise ValueError("native web search requires a web search API")
            required = {
                SearchReceiptKind.WEB_SEARCH_CALL,
                SearchReceiptKind.ANNOTATIONS_SOURCES,
            }
            if not required.issubset(set(self.search_receipts)):
                raise ValueError("native web search requires search-call and citation/source receipts")
        elif self.web_search_api is not WebSearchAPI.NONE or self.search_receipts:
            raise ValueError("unavailable native search cannot advertise an API or receipts")
        if len(self.reasoning_efforts) != len(set(self.reasoning_efforts)):
            raise ValueError("reasoning efforts must be unique")
        return self

    def has_strict_tools(self) -> bool:
        return self.protocol_conformance and self.structured_tool_calls and self.strict_tool_arguments

    def accepts_reasoning_effort(self, effort: str | ReasoningEffort) -> bool:
        try:
            normalized = effort if isinstance(effort, ReasoningEffort) else ReasoningEffort(str(effort))
        except ValueError:
            return False
        return normalized in self.reasoning_efforts


class CapabilityProfileAssessment(BaseModel):
    """Profile/evidence pair persisted atomically by Model Catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ModelCapabilityProfile
    evidence: ModelCapabilityProbeEvidence

    @model_validator(mode="after")
    def _validate_pair(self) -> Self:
        expected = build_profile_from_probe(self.evidence)
        if self.profile != expected:
            raise ValueError("capability profile is not derived from the supplied probe evidence")
        return self


class CapabilityProfileFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current: bool
    reasons: tuple[str, ...] = ()


def endpoint_fingerprint(
    *,
    model_name: str,
    base_url: str,
    generation_api: GenerationAPI | str | None,
) -> str:
    """Hash endpoint identity without API keys or mutable display metadata."""

    normalized_api = (
        generation_api.value
        if isinstance(generation_api, GenerationAPI)
        else str(generation_api or "none").strip()
    )
    return _canonical_hash(
        {
            "base_url": str(base_url or "").strip().rstrip("/"),
            "generation_api": normalized_api,
            "model_name": str(model_name or "").strip(),
        }
    )


def native_search_endpoint_fingerprint(base_url: str) -> str:
    """Bind the independently probed Responses SSE search endpoint."""
    return _canonical_hash(
        {
            "completion_boundary": "response.completed",
            "endpoint": native_search_endpoint(base_url),
            "transport": "sse",
        }
    )


def native_search_endpoint(base_url: str) -> str:
    """Resolve the single Responses endpoint used by probing and execution."""
    parsed = urlsplit(str(base_url or "").strip().rstrip("/"))
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    path = f"{path}/responses" if path else "/responses"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def build_profile_from_probe(evidence: ModelCapabilityProbeEvidence) -> ModelCapabilityProfile:
    """Derive runtime claims from checks; callers cannot elevate capabilities."""

    generation_api = evidence.generation_api
    protocol_conformance = bool(
        generation_api is not None and evidence.transport_conforms(generation_api)
    )
    structured_tool_calls = protocol_conformance and evidence.check_passed("structured_tool_calls")
    strict_tool_arguments = structured_tool_calls and evidence.check_passed("strict_tool_arguments")
    streaming = protocol_conformance and evidence.check_passed("streaming_termination")
    response_storage_disabled = protocol_conformance and evidence.check_passed("response_storage_disabled")
    reasoning_efforts = tuple(
        effort
        for effort in ReasoningEffort
        if protocol_conformance and evidence.check_passed(f"reasoning_effort:{effort.value}")
    )

    search_transport_conforms = (
        evidence.web_search_api is WebSearchAPI.RESPONSES_WEB_SEARCH
        and evidence.transport_conforms(GenerationAPI.RESPONSES)
    )
    required_receipts = {
        SearchReceiptKind.WEB_SEARCH_CALL,
        SearchReceiptKind.ANNOTATIONS_SOURCES,
    }
    native_web_search = (
        search_transport_conforms
        and evidence.check_passed("native_web_search_call")
        and evidence.check_passed("search_source_citations")
        and required_receipts.issubset(set(evidence.search_receipts))
    )

    return ModelCapabilityProfile(
        model_id=evidence.model_id,
        generation_api=generation_api,
        structured_tool_calls=structured_tool_calls,
        strict_tool_arguments=strict_tool_arguments,
        streaming=streaming,
        reasoning_efforts=reasoning_efforts,
        native_web_search=native_web_search,
        web_search_api=evidence.web_search_api if native_web_search else WebSearchAPI.NONE,
        search_receipts=evidence.search_receipts if native_web_search else (),
        structured_outputs=protocol_conformance and evidence.check_passed("structured_outputs"),
        vision=protocol_conformance and evidence.check_passed("vision"),
        response_storage_disabled=response_storage_disabled,
        protocol_conformance=protocol_conformance,
        transport_observations=evidence.transport_observations,
        observed_at=evidence.observed_at,
        probe_hash=evidence.evidence_hash(),
        endpoint_fingerprint=evidence.endpoint_fingerprint,
    )


def assess_profile_freshness(
    profile: ModelCapabilityProfile,
    evidence: ModelCapabilityProbeEvidence,
    *,
    model_id: str,
    model_name: str,
    base_url: str,
    generation_api: GenerationAPI | str | None,
    now: datetime | None = None,
    max_age: timedelta | None = None,
) -> CapabilityProfileFreshness:
    """Check profile hash, endpoint binding, derivation, and optional age."""

    reasons: list[str] = []
    expected_endpoint = endpoint_fingerprint(
        model_name=model_name,
        base_url=base_url,
        generation_api=generation_api,
    )
    if profile.model_id != model_id or evidence.model_id != model_id:
        reasons.append("model_id_mismatch")
    if profile.endpoint_fingerprint != expected_endpoint or evidence.endpoint_fingerprint != expected_endpoint:
        reasons.append("endpoint_changed")
    if profile.probe_hash != evidence.evidence_hash():
        reasons.append("probe_hash_mismatch")
    try:
        if profile != build_profile_from_probe(evidence):
            reasons.append("profile_not_probe_derived")
    except ValueError:
        reasons.append("profile_not_probe_derived")
    if max_age is not None:
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        if current_time - profile.observed_at > max_age:
            reasons.append("probe_stale")
    return CapabilityProfileFreshness(current=not reasons, reasons=tuple(dict.fromkeys(reasons)))


def unverified_capability_assessment(
    *,
    model_id: str,
    model_name: str,
    base_url: str,
    generation_api: GenerationAPI | None,
    observed_at: datetime | None = None,
) -> CapabilityProfileAssessment:
    """Create a fail-closed profile for a model that has not been probed."""

    observed = (observed_at or datetime.now(UTC)).astimezone(UTC)
    evidence = ModelCapabilityProbeEvidence(
        model_id=model_id,
        model_name=model_name,
        generation_api=generation_api,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name=model_name,
            base_url=base_url,
            generation_api=generation_api,
        ),
        observed_at=observed,
        checks=(
            CapabilityProbeCheck(
                name="capability_probe",
                status=ProbeCheckStatus.FAILED,
                detail_code="not_probed",
            ),
        ),
        transport_observations=(),
    )
    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


GPT56_RELEASE_MODEL_IDS = frozenset(
    {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
)


def gpt56_release_assessment(
    model_id: str,
    *,
    observed_at: datetime | None = None,
) -> CapabilityProfileAssessment:
    """Locked 2026-07-14 live-probe evidence for the GPT-5.6 release family."""

    if model_id not in GPT56_RELEASE_MODEL_IDS:
        raise ValueError(f"Unsupported GPT-5.6 release model: {model_id}")
    observed = (observed_at or datetime(2026, 7, 14, tzinfo=UTC)).astimezone(UTC)
    model_name = model_id
    base_url = "https://api.nainai.love/v1"
    evidence = ModelCapabilityProbeEvidence(
        model_id=model_id,
        model_name=model_name,
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name=model_name,
            base_url=base_url,
            generation_api=GenerationAPI.CHAT_COMPLETIONS,
        ),
        observed_at=observed,
        checks=(
            CapabilityProbeCheck(name="structured_tool_calls", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="strict_tool_arguments", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="streaming_termination", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="response_storage_disabled", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="reasoning_effort:low", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="reasoning_effort:medium", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="reasoning_effort:high", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="reasoning_effort:xhigh", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="native_web_search_call", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(name="search_source_citations", status=ProbeCheckStatus.PASSED),
            CapabilityProbeCheck(
                name="native_web_search_completed_event_boundary",
                status=ProbeCheckStatus.PASSED,
                detail_code=native_search_endpoint_fingerprint(base_url),
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
                detail_code="clean_done_and_close",
            ),
            GenerationTransportObservation(
                generation_api=GenerationAPI.RESPONSES,
                protocol_conformance=True,
                detail_code=native_search_endpoint_fingerprint(base_url),
            ),
        ),
    )
    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CapabilityProbeCheck",
    "CapabilityProfileAssessment",
    "CapabilityProfileFreshness",
    "GenerationAPI",
    "GenerationTransportObservation",
    "GPT56_RELEASE_MODEL_IDS",
    "ModelCapabilityProbeEvidence",
    "ModelCapabilityProfile",
    "ProbeCheckStatus",
    "SearchReceiptKind",
    "WebSearchAPI",
    "assess_profile_freshness",
    "build_profile_from_probe",
    "endpoint_fingerprint",
    "gpt56_release_assessment",
    "native_search_endpoint",
    "native_search_endpoint_fingerprint",
    "unverified_capability_assessment",
]
