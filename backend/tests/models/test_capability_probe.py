from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.models.capability_probe import (
    ModelProbeTarget,
    StreamProbeResult,
    probe_catalog_models,
    probe_model_capabilities,
)
from src.models.capability_profile import GenerationAPI, ModelTransportAPI


class _ProbeTransport:
    def __init__(
        self,
        *,
        arguments: str = '{"nonce":"WENJIN-PROBE","count":11}',
        clean_done: bool = True,
        search_error: ValueError | None = None,
    ) -> None:
        self.arguments = arguments
        self.clean_done = clean_done
        self.search_error = search_error
        self.payloads: list[dict[str, Any]] = []
        self.urls: list[str] = []

    async def post_json(self, **kwargs: Any) -> dict[str, Any]:
        self.payloads.append(kwargs["payload"])
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_probe",
                                "type": "function",
                                "function": {
                                    "name": "wenjin_capability_nonce",
                                    "arguments": self.arguments,
                                },
                            }
                        ]
                    }
                }
            ]
        }

    async def post_sse(self, **kwargs: Any) -> StreamProbeResult:
        self.payloads.append(kwargs["payload"])
        return StreamProbeResult(
            clean_done=self.clean_done,
            transport_complete=True,
        )

    async def post_native_search_sse(self, **kwargs: Any) -> dict[str, Any]:
        self.urls.append(kwargs["url"])
        self.payloads.append(kwargs["payload"])
        if self.search_error is not None:
            raise self.search_error
        return {
            "id": "resp_probe",
            "status": "completed",
            "output": [
                {
                    "id": "ws_probe",
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "official OpenAI website",
                        "sources": [
                            {
                                "url": "https://openai.com/",
                                "title": "OpenAI",
                            }
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "OpenAI",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://openai.com/",
                                    "title": "OpenAI",
                                    "start_index": 0,
                                    "end_index": 6,
                                }
                            ],
                        }
                    ],
                },
            ],
        }


class _CatalogProbeService:
    def __init__(self, records: dict[str, Any]) -> None:
        self.records = records
        self.calls: list[str] = []

    async def test_model(self, model_id: str) -> Any:
        self.calls.append(model_id)
        return self.records.get(model_id)


def _target() -> ModelProbeTarget:
    return ModelProbeTarget(
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://api.example/v1",
        api_key="sk-test-secret",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        default_headers={"X-Test": "1"},
    )


@pytest.mark.asyncio
async def test_probe_requires_strict_frame_and_sends_store_false() -> None:
    transport = _ProbeTransport()

    assessment = await probe_model_capabilities(
        _target(),
        transport=transport,
    )

    assert assessment.profile.has_strict_tools() is True
    assert assessment.profile.streaming is True
    assert assessment.profile.native_web_search is True
    assert [effort.value for effort in assessment.profile.reasoning_efforts] == [
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert all(payload["store"] is False for payload in transport.payloads)
    assert transport.payloads[0]["tool_choice"]["function"]["name"] == "wenjin_capability_nonce"
    assert transport.payloads[0]["tools"][0]["function"]["strict"] is True
    assert {
        payload["reasoning_effort"]
        for payload in transport.payloads
        if "reasoning_effort" in payload
    } == {
        "low",
        "medium",
        "high",
        "xhigh",
    }
    search_payload = transport.payloads[-1]
    assert search_payload["tools"] == [{"type": "web_search"}]
    assert search_payload["include"] == ["web_search_call.action.sources"]
    assert transport.urls == ["https://api.example/responses"]


@pytest.mark.asyncio
async def test_catalog_probe_uses_the_catalog_selected_model_set() -> None:
    assessment = await probe_model_capabilities(_target(), transport=_ProbeTransport())
    record = SimpleNamespace(
        model_id="gpt-5.6-sol",
        health_status="healthy",
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
    )
    service = _CatalogProbeService({record.model_id: record})

    payloads, ready = await probe_catalog_models(
        service,
        [record.model_id],
        require_native_search=True,
    )

    assert ready is True
    assert service.calls == [record.model_id]
    assert [payload["model_id"] for payload in payloads] == [record.model_id]


@pytest.mark.asyncio
async def test_catalog_probe_fails_closed_for_missing_or_empty_catalog_models() -> None:
    service = _CatalogProbeService({})

    missing_payloads, missing_ready = await probe_catalog_models(
        service,
        ["gpt-5.6-luna"],
        require_native_search=True,
    )
    empty_payloads, empty_ready = await probe_catalog_models(
        service,
        [],
        require_native_search=True,
    )

    assert missing_ready is False
    assert missing_payloads == [{"model_id": "gpt-5.6-luna", "status": "missing"}]
    assert empty_ready is False
    assert empty_payloads == []


@pytest.mark.asyncio
async def test_probe_rejects_malformed_function_arguments() -> None:
    assessment = await probe_model_capabilities(
        _target(),
        transport=_ProbeTransport(arguments=""),
    )

    assert assessment.profile.structured_tool_calls is False
    assert assessment.profile.strict_tool_arguments is False
    assert assessment.profile.protocol_conformance is False


@pytest.mark.asyncio
async def test_probe_rejects_stream_without_clean_done() -> None:
    assessment = await probe_model_capabilities(
        _target(),
        transport=_ProbeTransport(clean_done=False),
    )

    assert assessment.profile.streaming is False
    assert assessment.profile.protocol_conformance is False


@pytest.mark.asyncio
async def test_search_probe_failure_does_not_elevate_native_search() -> None:
    assessment = await probe_model_capabilities(
        _target(),
        transport=_ProbeTransport(search_error=ValueError("unsupported")),
    )

    assert assessment.profile.protocol_conformance is True
    assert assessment.profile.native_web_search is False
    assert assessment.evidence.check_passed("native_web_search_call") is False
    assert assessment.evidence.transport_conforms(ModelTransportAPI.RESPONSES) is False
