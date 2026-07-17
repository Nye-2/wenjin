from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.mission_runtime.production import ResponsesSSESearchExecutor
from src.services.model_catalog_cache import RuntimeModelConfig
from src.services.search import (
    ModelNativeSearchInput,
    ResponsesSearchSSEParser,
    ResponsesSearchSSEProtocolError,
    native_search_capability,
)
from tests.models.capability_fixtures import verified_capability_assessment

FIXTURES = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _runtime_model() -> RuntimeModelConfig:
    assessment = verified_capability_assessment("gpt-5.6-sol")
    return RuntimeModelConfig(
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        category="llm",
        provider="OpenAI",
        model="gpt-5.6-sol",
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


def test_parser_reconstructs_receipts_from_completed_output_items() -> None:
    parser = ResponsesSearchSSEParser()
    events = [
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "ws_incremental",
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": "OpenAI",
                    "sources": [
                        {"url": "https://openai.com/", "title": "OpenAI"}
                    ],
                },
            },
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {
                "id": "msg_incremental",
                "type": "message",
                "status": "completed",
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
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_incremental",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_incremental",
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "OpenAI",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        },
    ]

    completed = None
    for event in events:
        completed = parser.feed_line(f"event: {event['type']}") or completed
        completed = parser.feed_line(f"data: {json.dumps(event)}") or completed
        if completed is not None:
            break
        completed = parser.feed_line("") or completed

    assert completed is not None
    assert [item["type"] for item in completed["output"]] == [
        "web_search_call",
        "message",
    ]
    assert completed["output"][1]["content"][0]["annotations"][0]["type"] == (
        "url_citation"
    )


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


def test_release_probe_enables_receipt_backed_native_search() -> None:
    model = _runtime_model()
    capability = native_search_capability(model)

    assert capability.available is True
    assert capability.completed_event_boundary is True
    assert capability.reason_codes == ()
