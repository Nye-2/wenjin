"""Tests for typed pricing DataService client methods."""

from __future__ import annotations

import pytest

from src.dataservice_client.pricing_client import PricingDataServiceClientMixin


class _PricingClient(PricingDataServiceClientMixin):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs,
    ) -> dict:
        self.calls.append((method, path))
        return {
            "data": {
                "model_id": "gpt-5.6-terra",
                "model_policy": {
                    "id": "model-policy-1",
                    "policy_key": "terra",
                    "policy_kind": "model_usage",
                    "name": "Terra pricing",
                    "enabled": True,
                    "version": 2,
                    "config": {"free_tokens": 100000},
                },
                "global_policy": None,
            }
        }


@pytest.mark.asyncio
async def test_resolve_model_usage_pricing_uses_canonical_endpoint() -> None:
    client = _PricingClient()

    resolved = await client.resolve_model_usage_pricing("gpt-5.6-terra")

    assert client.calls == [
        ("GET", "/internal/v1/pricing-policies/model-usage/gpt-5.6-terra")
    ]
    assert resolved.model_policy.policy_key == "terra"
    assert resolved.model_policy.config["free_tokens"] == 100000
