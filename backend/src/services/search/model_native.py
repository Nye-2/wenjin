"""Provider-receipt-only model-native web search tool."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.contracts.reasoning import ReasoningEffort
from src.models.capability_profile import (
    SearchReceiptKind,
    WebSearchAPI,
    native_search_endpoint_fingerprint,
)
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    get_runtime_model_config,
    resolve_runtime_model_id,
)
from src.tools.orchestrator import (
    SideEffectClass,
    SourceReference,
    ToolCallerKind,
    ToolDispatchError,
    ToolErrorType,
    ToolHandlerResult,
    ToolKind,
    ToolOperation,
    ToolOutcomeStatus,
    ToolReference,
    VerificationStatus,
    build_tool_registration,
)
from src.tools.orchestrator.catalog import ToolRegistration

MODEL_NATIVE_SEARCH_TOOL_ID = "research.search_web"


def build_native_search_payload(
    *,
    model_name: str,
    query: str,
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH,
) -> dict[str, Any]:
    """Build the canonical provider-native Responses search request."""
    return {
        "model": model_name,
        "input": query,
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "store": False,
        "stream": True,
        "reasoning": {"effort": reasoning_effort.value},
    }


class ModelNativeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)
    year_range: tuple[int, int] | None = None

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("query cannot be empty")
        return normalized

    @field_validator("year_range")
    @classmethod
    def _validate_year_range(
        cls,
        value: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        if value is None:
            return None
        if value[0] < 1800 or value[1] > 2200 or value[0] > value[1]:
            raise ValueError("year_range is invalid")
        return value


class NativeSearchCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    title: str
    start_index: int | None = None
    end_index: int | None = None


class NativeSearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    title: str


class NativeSearchReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str
    search_call_ids: tuple[str, ...]
    queries: tuple[str, ...]
    sources: tuple[NativeSearchSource, ...]
    citations: tuple[NativeSearchCitation, ...]


class NativeSearchCapability(BaseModel):
    """Independent Responses SSE search capability derived from probe evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    web_search_api: WebSearchAPI = WebSearchAPI.NONE
    receipt_kinds: tuple[SearchReceiptKind, ...] = ()
    completed_event_boundary: bool = False
    endpoint_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason_codes: tuple[str, ...] = ()


def native_search_capability(model: RuntimeModelConfig) -> NativeSearchCapability:
    freshness = model.capability_freshness()
    evidence = model.capability_probe
    expected_endpoint = native_search_endpoint_fingerprint(model.base_url)
    boundary_check = next(
        (
            check
            for check in evidence.checks
            if check.name == "native_web_search_completed_event_boundary"
        ),
        None,
    )
    required_receipts = {
        SearchReceiptKind.WEB_SEARCH_CALL,
        SearchReceiptKind.ANNOTATIONS_SOURCES,
    }
    reasons: list[str] = []
    if not freshness.current:
        reasons.append("model_profile_stale")
    if evidence.web_search_api is not WebSearchAPI.RESPONSES_WEB_SEARCH:
        reasons.append("responses_search_not_probed")
    if not evidence.check_passed("native_web_search_call"):
        reasons.append("search_call_not_verified")
    if not evidence.check_passed("search_source_citations"):
        reasons.append("search_citations_not_verified")
    if not required_receipts.issubset(set(evidence.search_receipts)):
        reasons.append("search_receipts_incomplete")
    if boundary_check is None or not evidence.check_passed(
        "native_web_search_completed_event_boundary"
    ):
        reasons.append("completed_event_boundary_not_verified")
    elif boundary_check.detail_code != expected_endpoint:
        reasons.append("search_endpoint_changed")
    return NativeSearchCapability(
        available=not reasons,
        web_search_api=(
            evidence.web_search_api if not reasons else WebSearchAPI.NONE
        ),
        receipt_kinds=(evidence.search_receipts if not reasons else ()),
        completed_event_boundary=not reasons,
        endpoint_fingerprint=(expected_endpoint if not reasons else None),
        reason_codes=tuple(reasons),
    )


class NativeSearchExecutor(Protocol):
    """Provider adapter enabled only after its API passes transport probes."""

    async def __call__(
        self,
        *,
        model: RuntimeModelConfig,
        request: ModelNativeSearchInput,
    ) -> dict[str, Any]: ...


ModelResolver = Callable[[str], RuntimeModelConfig | None]
SearchCapabilityResolver = Callable[[RuntimeModelConfig], NativeSearchCapability]


class ModelNativeSearchHandler:
    def __init__(
        self,
        *,
        executor: NativeSearchExecutor | None,
        model_resolver: ModelResolver = get_runtime_model_config,
        capability_resolver: SearchCapabilityResolver = native_search_capability,
    ) -> None:
        self._executor = executor
        self._model_resolver = model_resolver
        self._capability_resolver = capability_resolver

    async def __call__(
        self,
        operation: ToolOperation,
        arguments: BaseModel,
    ) -> ToolHandlerResult:
        request = ModelNativeSearchInput.model_validate(arguments.model_dump())
        requested_model_id = operation.model_id
        try:
            model_id = (
                requested_model_id
                if requested_model_id
                else resolve_runtime_model_id(None)
            )
        except ValueError:
            return _capability_gap("No selected model is available for verified web search.")
        model = self._model_resolver(model_id)
        if model is None:
            return _capability_gap("The selected model is unavailable to the runtime.")
        capability = self._capability_resolver(model)
        if not capability.available:
            return _capability_gap(
                "Verified model-native web search is not available for the selected model.",
                reason_codes=capability.reason_codes,
            )
        if self._executor is None:
            raise ToolDispatchError(
                ToolErrorType.TOOL_UNAVAILABLE,
                "The verified native-search transport adapter is not installed.",
            )

        provider_response = await self._executor(model=model, request=request)
        try:
            receipt = parse_native_search_receipt(provider_response)
        except NativeSearchReceiptError as exc:
            raise ToolDispatchError(
                ToolErrorType.PROVENANCE_MISSING,
                "The provider response did not include a complete search receipt and citations.",
            ) from exc

        source_refs = _source_references(receipt)
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary=(
                f"Verified web search returned {len(source_refs)} cited source(s) "
                f"for: {request.query}"
            ),
            evidence_refs=(
                ToolReference(
                    ref_id=f"provider-search:{receipt.response_id}",
                    kind="provider_search_receipt",
                    metadata={
                        "response_id": receipt.response_id,
                        "search_call_ids": list(receipt.search_call_ids),
                        "queries": list(receipt.queries),
                    },
                ),
            ),
            source_refs=source_refs,
            confidence=1.0,
            verification_status=VerificationStatus.PROVIDER_RECEIPT,
        )


class NativeSearchReceiptError(ValueError):
    pass


def model_native_search_registration(
    *,
    executor: NativeSearchExecutor | None = None,
    model_resolver: ModelResolver = get_runtime_model_config,
    capability_resolver: SearchCapabilityResolver = native_search_capability,
) -> ToolRegistration:
    handler = ModelNativeSearchHandler(
        executor=executor,
        model_resolver=model_resolver,
        capability_resolver=capability_resolver,
    )
    return build_tool_registration(
        tool_id=MODEL_NATIVE_SEARCH_TOOL_ID,
        tool_version="1.0.0",
        kind=ToolKind.READ,
        input_model=ModelNativeSearchInput,
        handler=handler,
        side_effect_class=SideEffectClass.NONE,
        allowed_callers=(
            ToolCallerKind.WORKSPACE_AGENT,
            ToolCallerKind.SUBAGENT,
        ),
        required_permissions=("external_research",),
        network_profile="model_provider_native_search",
        budget_class="research_search",
        default_timeout_seconds=90,
        provenance_requirements=(
            "provider_web_search_call",
            "provider_url_citations",
            "provider_source_metadata",
        ),
    )


def parse_native_search_receipt(response: dict[str, Any]) -> NativeSearchReceipt:
    """Accept only a completed Responses object with native search receipts."""

    if not isinstance(response, dict) or response.get("status") != "completed":
        raise NativeSearchReceiptError("response did not complete cleanly")
    response_id = str(response.get("id") or "").strip()
    outputs = response.get("output")
    if not response_id or not isinstance(outputs, list):
        raise NativeSearchReceiptError("response identity or output is missing")

    call_ids: list[str] = []
    queries: list[str] = []
    source_by_url: dict[str, NativeSearchSource] = {}
    citations: list[NativeSearchCitation] = []

    for output in outputs:
        if not isinstance(output, dict):
            continue
        if output.get("type") == "web_search_call":
            if output.get("status") != "completed":
                raise NativeSearchReceiptError("web search call did not complete")
            call_id = str(output.get("id") or "").strip()
            if not call_id:
                raise NativeSearchReceiptError("web search call id is missing")
            call_ids.append(call_id)
            action = output.get("action")
            if isinstance(action, dict):
                query = str(action.get("query") or "").strip()
                if query:
                    queries.append(query)
                for item in action.get("sources") or []:
                    _collect_source(item, source_by_url)
        if output.get("type") == "message":
            for content in output.get("content") or []:
                if not isinstance(content, dict) or content.get("type") != "output_text":
                    continue
                for annotation in content.get("annotations") or []:
                    citation = _citation_from_annotation(annotation)
                    if citation is None:
                        continue
                    citations.append(citation)
                    source_by_url.setdefault(
                        citation.url,
                        NativeSearchSource(url=citation.url, title=citation.title),
                    )

    if not call_ids:
        raise NativeSearchReceiptError("provider returned no web_search_call")
    if not citations:
        raise NativeSearchReceiptError("provider returned no URL citations")
    if not source_by_url:
        raise NativeSearchReceiptError("provider returned no source metadata")
    return NativeSearchReceipt(
        response_id=response_id,
        search_call_ids=tuple(call_ids),
        queries=tuple(dict.fromkeys(queries)),
        sources=tuple(source_by_url.values()),
        citations=tuple(citations),
    )


def _collect_source(
    item: Any,
    source_by_url: dict[str, NativeSearchSource],
) -> None:
    if not isinstance(item, dict):
        return
    url = _valid_url(item.get("url"))
    if url is None:
        return
    title = str(item.get("title") or item.get("name") or url).strip()[:500]
    source_by_url.setdefault(url, NativeSearchSource(url=url, title=title))


def _citation_from_annotation(item: Any) -> NativeSearchCitation | None:
    if not isinstance(item, dict) or item.get("type") != "url_citation":
        return None
    url = _valid_url(item.get("url"))
    if url is None:
        return None
    title = str(item.get("title") or url).strip()[:500]
    return NativeSearchCitation(
        url=url,
        title=title,
        start_index=_optional_int(item.get("start_index")),
        end_index=_optional_int(item.get("end_index")),
    )


def _source_references(receipt: NativeSearchReceipt) -> tuple[SourceReference, ...]:
    observed_at = datetime.now(UTC)
    citation_by_url: dict[str, list[NativeSearchCitation]] = {}
    for citation in receipt.citations:
        citation_by_url.setdefault(citation.url, []).append(citation)
    references: list[SourceReference] = []
    for source in receipt.sources:
        claim_refs = tuple(
            f"{receipt.response_id}:{citation.start_index or 0}-{citation.end_index or 0}"
            for citation in citation_by_url.get(source.url, [])
        )
        references.append(
            SourceReference(
                source_id=f"web:{hashlib.sha256(source.url.encode('utf-8')).hexdigest()}",
                canonical_url=source.url,
                title=source.title,
                observed_at=observed_at,
                supported_claim_refs=claim_refs,
                verification_status=VerificationStatus.PROVIDER_RECEIPT,
            )
        )
    return tuple(references)


def _capability_gap(
    summary: str,
    *,
    reason_codes: tuple[str, ...] = (),
) -> ToolHandlerResult:
    return ToolHandlerResult(
        status=ToolOutcomeStatus.PARTIAL,
        summary=summary,
        evidence_refs=(
            ToolReference(
                ref_id="gap:native-web-search-unavailable",
                kind="evidence_gap",
                metadata={
                    "reason": ToolErrorType.CAPABILITY_UNVERIFIED.value,
                    "reason_codes": list(reason_codes),
                },
            ),
        ),
        verification_status=VerificationStatus.UNVERIFIED,
        recommended_next_action=(
            "Configure a model endpoint whose native search and transport both pass the live probe."
        ),
    )


def _valid_url(value: Any) -> str | None:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "MODEL_NATIVE_SEARCH_TOOL_ID",
    "ModelNativeSearchHandler",
    "ModelNativeSearchInput",
    "NativeSearchCitation",
    "NativeSearchCapability",
    "NativeSearchExecutor",
    "NativeSearchReceipt",
    "NativeSearchReceiptError",
    "NativeSearchSource",
    "build_native_search_payload",
    "model_native_search_registration",
    "native_search_capability",
    "parse_native_search_receipt",
]
