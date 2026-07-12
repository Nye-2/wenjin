from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.mission_runtime.production import ResponsesSSESearchExecutor
from src.models.capability_profile import (
    gpt55_release_assessment,
    native_search_endpoint_fingerprint,
)
from src.services.model_catalog_cache import RuntimeModelConfig
from src.services.search import (
    ModelNativeSearchInput,
    ResponsesSearchSSEParser,
    ResponsesSearchSSEProtocolError,
    native_search_capability,
)

FIXTURES = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _runtime_model() -> RuntimeModelConfig:
    assessment = gpt55_release_assessment()
    return RuntimeModelConfig(
        id="gpt-5.5",
        name="GPT-5.5",
        category="llm",
        provider="OpenAI",
        model="gpt-5.5",
        api_key="sk-test",
        base_url="https://api.nainai.love/v1",
        generation_api=assessment.profile.generation_api,
        max_tokens=128000,
        temperature=0.2,
        timeout_seconds=60,
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


def _parse_fixture(name: str) -> dict:
    parser = ResponsesSearchSSEParser()
    completed = None
    for line in _fixture(name).split("\n"):
        value = parser.feed_line(line)
        if value is not None:
            completed = value
            break
    if completed is None:
        completed = parser.finish()
    return completed


def test_parser_stops_at_verified_completed_event_fixture() -> None:
    response = _parse_fixture("responses_search_completed.sse")

    assert response["id"] == "resp_search_1"
    assert response["output"][0]["type"] == "web_search_call"


def test_parser_rejects_completed_event_without_url_citations() -> None:
    with pytest.raises(
        ResponsesSearchSSEProtocolError,
        match="complete search receipts",
    ):
        _parse_fixture("responses_search_missing_citation.sse")


def test_parser_rejects_stream_without_completed_event() -> None:
    with pytest.raises(
        ResponsesSearchSSEProtocolError,
        match="ended before",
    ):
        _parse_fixture("responses_search_incomplete.sse")


class _BrokenAfterCompleted(httpx.AsyncByteStream):
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_after_boundary = False
        self.closed = False

    async def __aiter__(self):
        yield self.payload
        self.read_after_boundary = True
        raise httpx.RemoteProtocolError("peer closed incomplete chunked body")

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_executor_closes_at_completed_boundary_before_peer_error() -> None:
    stream = _BrokenAfterCompleted(
        _fixture("responses_search_completed.sse").encode("utf-8")
    )
    observed_payload: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=stream,
        )

    result = await ResponsesSSESearchExecutor(
        transport=httpx.MockTransport(handler)
    )(
        model=_runtime_model(),
        request=ModelNativeSearchInput(query="federated LoRA"),
    )

    assert result["status"] == "completed"
    assert observed_payload["stream"] is True
    assert observed_payload["tools"] == [{"type": "web_search"}]
    assert observed_payload["tool_choice"] == "required"
    assert stream.closed is True
    assert stream.read_after_boundary is False


def test_release_probe_records_failed_boundary_and_endpoint_fingerprint() -> None:
    model = _runtime_model()
    capability = native_search_capability(model)
    boundary = next(
        check
        for check in model.capability_probe.checks
        if check.name == "native_web_search_completed_event_boundary"
    )

    assert capability.available is False
    assert capability.completed_event_boundary is False
    assert "completed_event_boundary_not_verified" in capability.reason_codes
    assert boundary.detail_code == native_search_endpoint_fingerprint(model.base_url)
