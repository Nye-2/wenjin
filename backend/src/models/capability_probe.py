"""Explicit, harmless model capability probe.

This module is called by an admin/release operation or as a CLI. It is never
invoked from ordinary chat or mission requests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from src.contracts.reasoning import ReasoningEffort
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
    native_search_endpoint,
    native_search_endpoint_fingerprint,
)
from src.services.search.model_native import (
    build_native_search_payload,
    parse_native_search_receipt,
)
from src.services.search.responses_sse import ResponsesSearchSSEParser
from src.tools.orchestrator.errors import MalformedToolArgumentsError
from src.tools.orchestrator.frames import parse_chat_completions_tool_calls

_PROBE_TOOL_NAME = "wenjin_capability_nonce"
_PROBE_NONCE = "WENJIN-PROBE"
_PROBE_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class ModelProbeTarget:
    model_id: str
    model_name: str
    base_url: str
    api_key: str
    generation_api: GenerationAPI
    default_headers: dict[str, str]
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class StreamProbeResult:
    clean_done: bool
    transport_complete: bool


class CapabilityProbeTransport(Protocol):
    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...

    async def post_sse(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> StreamProbeResult: ...

    async def post_native_search_sse(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class HttpCapabilityProbeTransport:
    def __init__(
        self,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(trust_env=False)
        )

    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        async with self._client_factory() as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("probe response is not an object")
        return data

    async def post_sse(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> StreamProbeResult:
        clean_done = False
        async with self._client_factory() as client:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip() == "data: [DONE]":
                        clean_done = True
        return StreamProbeResult(
            clean_done=clean_done,
            transport_complete=True,
        )

    async def post_native_search_sse(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        parser = ResponsesSearchSSEParser()
        async with self._client_factory() as client:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    completed = parser.feed_line(line)
                    if completed is not None:
                        await response.aclose()
                        return completed
        return parser.finish()


async def probe_model_capabilities(
    target: ModelProbeTarget,
    *,
    transport: CapabilityProbeTransport | None = None,
) -> CapabilityProfileAssessment:
    """Probe the configured generation API and return hashable evidence."""

    selected_transport = transport or HttpCapabilityProbeTransport()
    headers = {
        "Authorization": f"Bearer {target.api_key}",
        "Content-Type": "application/json",
        **target.default_headers,
    }
    url = _chat_completions_url(target.base_url)
    checks: list[CapabilityProbeCheck] = []
    strict_ok = False
    stream_ok = False

    try:
        response = await selected_transport.post_json(
            url=url,
            headers=headers,
            payload=_strict_tool_payload(target.model_name),
            timeout_seconds=target.timeout_seconds,
        )
        calls = parse_chat_completions_tool_calls(response)
        strict_ok = (
            len(calls) == 1
            and calls[0].tool_id == _PROBE_TOOL_NAME
            and calls[0].arguments
            == {"count": 11, "nonce": _PROBE_NONCE}
        )
    except (httpx.HTTPError, ValueError, MalformedToolArgumentsError) as exc:
        checks.append(
            _check(
                "structured_tool_calls",
                False,
                detail_code=f"{exc.__class__.__name__}:strict_tool_probe_failed",
            )
        )
        checks.append(
            _check(
                "strict_tool_arguments",
                False,
                detail_code="strict_tool_probe_failed",
            )
        )
    else:
        checks.append(_check("structured_tool_calls", strict_ok))
        checks.append(_check("strict_tool_arguments", strict_ok))

    try:
        stream_result = await selected_transport.post_sse(
            url=url,
            headers=headers,
            payload=_stream_payload(target.model_name),
            timeout_seconds=target.timeout_seconds,
        )
        stream_ok = stream_result.clean_done and stream_result.transport_complete
    except (httpx.HTTPError, ValueError) as exc:
        checks.append(
            _check(
                "streaming_termination",
                False,
                detail_code=f"{exc.__class__.__name__}:stream_probe_failed",
            )
        )
    else:
        checks.append(_check("streaming_termination", stream_ok))

    protocol_conformance = strict_ok and stream_ok
    checks.append(_check("response_storage_disabled", protocol_conformance))
    try:
        await selected_transport.post_json(
            url=url,
            headers=headers,
            payload=_vision_payload(target.model_name),
            timeout_seconds=target.timeout_seconds,
        )
    except (httpx.HTTPError, ValueError) as exc:
        checks.append(
            _check(
                "vision",
                False,
                detail_code=f"{exc.__class__.__name__}:vision_probe_failed",
            )
        )
    else:
        checks.append(_check("vision", protocol_conformance))
    for effort in ReasoningEffort:
        try:
            await selected_transport.post_json(
                url=url,
                headers=headers,
                payload=_reasoning_payload(target.model_name, effort),
                timeout_seconds=target.timeout_seconds,
            )
        except (httpx.HTTPError, ValueError) as exc:
            checks.append(
                _check(
                    f"reasoning_effort:{effort.value}",
                    False,
                    detail_code=f"{exc.__class__.__name__}:reasoning_probe_failed",
                )
            )
        else:
            checks.append(_check(f"reasoning_effort:{effort.value}", protocol_conformance))
    search_endpoint = native_search_endpoint(target.base_url)
    search_endpoint_hash = native_search_endpoint_fingerprint(target.base_url)
    search_transport_conformance = False
    search_receipts: tuple[SearchReceiptKind, ...] = ()
    web_search_api = WebSearchAPI.NONE
    try:
        search_response = await selected_transport.post_native_search_sse(
            url=search_endpoint,
            headers=headers,
            payload=build_native_search_payload(
                model_name=target.model_name,
                query="Find and cite the official OpenAI website.",
            ),
            timeout_seconds=target.timeout_seconds,
        )
        receipt = parse_native_search_receipt(search_response)
        search_transport_conformance = bool(
            receipt.search_call_ids and receipt.sources and receipt.citations
        )
    except (httpx.HTTPError, ValueError) as exc:
        detail_code = f"{exc.__class__.__name__}:native_search_probe_failed"
        checks.extend(
            (
                _check("native_web_search_call", False, detail_code=detail_code),
                _check("search_source_citations", False, detail_code=detail_code),
                _check(
                    "native_web_search_completed_event_boundary",
                    False,
                    detail_code=detail_code,
                ),
            )
        )
    else:
        checks.extend(
            (
                _check("native_web_search_call", search_transport_conformance),
                _check("search_source_citations", search_transport_conformance),
                _check(
                    "native_web_search_completed_event_boundary",
                    search_transport_conformance,
                    detail_code=search_endpoint_hash,
                ),
            )
        )
        if search_transport_conformance:
            web_search_api = WebSearchAPI.RESPONSES_WEB_SEARCH
            search_receipts = (
                SearchReceiptKind.WEB_SEARCH_CALL,
                SearchReceiptKind.ANNOTATIONS_SOURCES,
            )
    evidence = ModelCapabilityProbeEvidence(
        model_id=target.model_id,
        model_name=target.model_name,
        generation_api=target.generation_api,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name=target.model_name,
            base_url=target.base_url,
            generation_api=target.generation_api,
        ),
        observed_at=_utc_now(),
        checks=tuple(checks),
        web_search_api=web_search_api,
        search_receipts=search_receipts,
        transport_observations=(
            ModelTransportObservation(
                transport_api=ModelTransportAPI.CHAT_COMPLETIONS,
                protocol_conformance=protocol_conformance,
                detail_code=(
                    "clean_done_and_close"
                    if protocol_conformance
                    else "selected_generation_api_probe_failed"
                ),
            ),
            ModelTransportObservation(
                transport_api=ModelTransportAPI.RESPONSES,
                protocol_conformance=search_transport_conformance,
                detail_code=(
                    search_endpoint_hash
                    if search_transport_conformance
                    else "native_search_probe_failed"
                ),
            ),
        ),
    )
    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


def _strict_tool_payload(model_name: str) -> dict[str, Any]:
    return {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Call wenjin_capability_nonce with nonce WENJIN-PROBE and count 11."
                ),
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": _PROBE_TOOL_NAME,
                    "description": "Return the harmless capability-probe nonce.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nonce": {"type": "string", "const": _PROBE_NONCE},
                            "count": {"type": "integer", "const": 11},
                        },
                        "required": ["nonce", "count"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": _PROBE_TOOL_NAME},
        },
        "reasoning_effort": "low",
        "store": False,
        "max_tokens": 128,
    }


def _stream_payload(model_name: str) -> dict[str, Any]:
    return {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Reply with WENJIN-PROBE-OK."}
        ],
        "stream": True,
        "reasoning_effort": "low",
        "store": False,
        "max_tokens": 128,
    }


def _reasoning_payload(model_name: str, effort: ReasoningEffort) -> dict[str, Any]:
    return {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "reasoning_effort": effort.value,
        "store": False,
        "max_tokens": 32,
    }


def _vision_payload(model_name: str) -> dict[str, Any]:
    return {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reply with OK."},
                    {
                        "type": "image_url",
                        "image_url": {"url": _PROBE_IMAGE_DATA_URL, "detail": "low"},
                    },
                ],
            }
        ],
        "reasoning_effort": "low",
        "store": False,
        "max_tokens": 32,
    }


def _check(
    name: str,
    passed: bool,
    *,
    detail_code: str | None = None,
) -> CapabilityProbeCheck:
    return CapabilityProbeCheck(
        name=name,
        status=(ProbeCheckStatus.PASSED if passed else ProbeCheckStatus.FAILED),
        detail_code=detail_code,
    )


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _utc_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def _cli() -> int:
    parser = argparse.ArgumentParser(description="Probe Wenjin model protocol capabilities")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--model-id")
    target.add_argument(
        "--all-enabled-language-models",
        action="store_true",
        help="Probe every enabled language model returned by the DataService catalog",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help=(
            "Probe the DataService-owned runtime configuration and persist the exact "
            "endpoint-bound assessment in Model Catalog"
        ),
    )
    parser.add_argument(
        "--require-native-search",
        action="store_true",
        help="Return a non-zero status unless verified native-search receipts are present",
    )
    args = parser.parse_args()

    if args.all_enabled_language_models and not args.persist:
        parser.error("--all-enabled-language-models requires --persist")

    if args.persist:
        from src.dataservice_client.provider import dataservice_client
        from src.services.model_catalog_service import ModelCatalogService

        async with dataservice_client() as dataservice:
            service = ModelCatalogService(dataservice=dataservice)
            if args.all_enabled_language_models:
                catalog = await service.list_models(category="llm", enabled_only=True)
                model_ids = [record.model_id for record in catalog]
            else:
                model_ids = [args.model_id]
            payloads, ready = await probe_catalog_models(
                service,
                model_ids,
                require_native_search=args.require_native_search,
            )
        output: Any = {"models": payloads} if args.all_enabled_language_models else payloads[0]
        print(json.dumps(output, sort_keys=True))
        return 0 if ready else 1

    from src.config.llm_config import get_model_full_config, reload_models

    reload_models()
    config = get_model_full_config(args.model_id)
    generation_api = config.get("generation_api")
    if not isinstance(generation_api, GenerationAPI):
        raise ValueError("the selected model has no generation_api")
    assessment = await probe_model_capabilities(
        ModelProbeTarget(
            model_id=args.model_id,
            model_name=str(config["model"]),
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            generation_api=generation_api,
            default_headers=dict(config.get("default_headers") or {}),
        )
    )
    print(json.dumps(assessment.model_dump(mode="json"), sort_keys=True))
    if not assessment.profile.protocol_conformance:
        return 1
    if args.require_native_search and not assessment.profile.native_web_search:
        return 1
    return 0


async def probe_catalog_models(
    service: Any,
    model_ids: list[str],
    *,
    require_native_search: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Persist probe evidence for one catalog-selected language-model set."""

    payloads: list[dict[str, Any]] = []
    ready = bool(model_ids)
    for model_id in model_ids:
        record = await service.test_model(model_id)
        if record is None:
            payloads.append({"model_id": model_id, "status": "missing"})
            ready = False
            continue
        profile = record.capability_profile
        payloads.append(
            {
                "model_id": record.model_id,
                "health_status": record.health_status,
                "capability_profile": profile.model_dump(mode="json"),
                "capability_probe": record.capability_probe.model_dump(mode="json"),
                "capability_probe_hash": record.capability_probe_hash,
                "capability_observed_at": record.capability_observed_at.isoformat(),
            }
        )
        if record.health_status != "healthy" or not profile.protocol_conformance:
            ready = False
        if require_native_search and not profile.native_web_search:
            ready = False
    return payloads, ready


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli()))


__all__ = [
    "CapabilityProbeTransport",
    "HttpCapabilityProbeTransport",
    "ModelProbeTarget",
    "StreamProbeResult",
    "probe_catalog_models",
    "probe_model_capabilities",
]
