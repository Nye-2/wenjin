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

from src.models.capability_profile import (
    CapabilityProbeCheck,
    CapabilityProfileAssessment,
    GenerationAPI,
    GenerationTransportObservation,
    ModelCapabilityProbeEvidence,
    ProbeCheckStatus,
    ReasoningEffort,
    build_profile_from_probe,
    endpoint_fingerprint,
)
from src.tools.orchestrator.errors import MalformedToolArgumentsError
from src.tools.orchestrator.frames import parse_chat_completions_tool_calls

_PROBE_TOOL_NAME = "wenjin_capability_nonce"
_PROBE_NONCE = "WENJIN-PROBE"


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


async def probe_model_capabilities(
    target: ModelProbeTarget,
    *,
    transport: CapabilityProbeTransport | None = None,
) -> CapabilityProfileAssessment:
    """Probe the configured generation API and return hashable evidence."""

    selected_transport = transport or HttpCapabilityProbeTransport()
    if target.generation_api is not GenerationAPI.CHAT_COMPLETIONS:
        evidence = _failed_evidence(
            target,
            detail_code="generation_api_not_enabled_in_runtime",
        )
        return CapabilityProfileAssessment(
            profile=build_profile_from_probe(evidence),
            evidence=evidence,
        )

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
    reasoning_support = {ReasoningEffort.XHIGH: strict_ok}
    for effort in (ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH):
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
            reasoning_support[effort] = True
            checks.append(_check(f"reasoning_effort:{effort.value}", protocol_conformance))
    checks.append(
        _check(
            "reasoning_effort:xhigh",
            protocol_conformance and reasoning_support[ReasoningEffort.XHIGH],
        )
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
        transport_observations=(
            GenerationTransportObservation(
                generation_api=target.generation_api,
                protocol_conformance=protocol_conformance,
                detail_code=(
                    "clean_done_and_close"
                    if protocol_conformance
                    else "selected_generation_api_probe_failed"
                ),
            ),
        ),
    )
    return CapabilityProfileAssessment(
        profile=build_profile_from_probe(evidence),
        evidence=evidence,
    )


def _failed_evidence(
    target: ModelProbeTarget,
    *,
    detail_code: str,
) -> ModelCapabilityProbeEvidence:
    return ModelCapabilityProbeEvidence(
        model_id=target.model_id,
        model_name=target.model_name,
        generation_api=target.generation_api,
        endpoint_fingerprint=endpoint_fingerprint(
            model_name=target.model_name,
            base_url=target.base_url,
            generation_api=target.generation_api,
        ),
        observed_at=_utc_now(),
        checks=(
            CapabilityProbeCheck(
                name="capability_probe",
                status=ProbeCheckStatus.FAILED,
                detail_code=detail_code,
            ),
        ),
        transport_observations=(
            GenerationTransportObservation(
                generation_api=target.generation_api,
                protocol_conformance=False,
                detail_code=detail_code,
            ),
        ),
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
        "reasoning_effort": "xhigh",
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
        "reasoning_effort": "xhigh",
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
    parser = argparse.ArgumentParser(description="Probe one env-configured Wenjin model")
    parser.add_argument("--model-id", required=True)
    args = parser.parse_args()

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
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli()))


__all__ = [
    "CapabilityProbeTransport",
    "HttpCapabilityProbeTransport",
    "ModelProbeTarget",
    "StreamProbeResult",
    "probe_model_capabilities",
]
