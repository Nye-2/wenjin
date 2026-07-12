from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from src.models.capability_probe import (
    ModelProbeTarget,
    StreamProbeResult,
    probe_model_capabilities,
)
from src.models.capability_profile import GenerationAPI


class _ProbeTransport:
    def __init__(
        self,
        *,
        arguments: str = '{"nonce":"WENJIN-PROBE","count":11}',
        clean_done: bool = True,
    ) -> None:
        self.arguments = arguments
        self.clean_done = clean_done
        self.payloads: list[dict[str, Any]] = []

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


def _target() -> ModelProbeTarget:
    return ModelProbeTarget(
        model_id="gpt-5.5",
        model_name="gpt-5.5",
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
    assert assessment.profile.native_web_search is False
    assert [effort.value for effort in assessment.profile.reasoning_efforts] == [
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert all(payload["store"] is False for payload in transport.payloads)
    assert transport.payloads[0]["tool_choice"]["function"]["name"] == "wenjin_capability_nonce"
    assert transport.payloads[0]["tools"][0]["function"]["strict"] is True
    assert {payload["reasoning_effort"] for payload in transport.payloads} == {
        "low",
        "medium",
        "high",
        "xhigh",
    }


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
async def test_responses_transport_is_not_probed_or_used_as_a_fallback() -> None:
    transport = _ProbeTransport()

    assessment = await probe_model_capabilities(
        replace(_target(), generation_api=GenerationAPI.RESPONSES),
        transport=transport,
    )

    assert assessment.profile.protocol_conformance is False
    assert assessment.profile.native_web_search is False
    assert transport.payloads == []
    assert assessment.evidence.transport_observations[0].detail_code == (
        "generation_api_not_enabled_in_runtime"
    )
