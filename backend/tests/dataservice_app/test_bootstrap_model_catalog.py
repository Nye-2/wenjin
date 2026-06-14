"""Tests for DataService model catalog bootstrap wiring."""

from __future__ import annotations

import pytest

from src.dataservice.domains.pricing.seed_loader import DEFAULT_MODEL_USAGE_POLICY_KEY
from src.dataservice_app import bootstrap_model_catalog


@pytest.mark.asyncio
async def test_seed_model_catalog_from_env_loads_pricing_defaults_before_models(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[object] = []

    class _PricingService:
        def __init__(self, session: object) -> None:
            events.append(("pricing-service", session))

    class _PricingLoader:
        def __init__(self, service: _PricingService, *, admin_id: str | None = None) -> None:
            events.append(("pricing-loader", admin_id))

        async def load_defaults(self) -> int:
            events.append("pricing-loaded")
            return 5

    class _ModelService:
        def __init__(
            self,
            session: object,
            *,
            allow_private_network: bool,
            require_https: bool,
        ) -> None:
            events.append(("model-service", allow_private_network, require_https))

    class _ModelLoader:
        def __init__(
            self,
            service: _ModelService,
            *,
            admin_id: str | None = None,
            default_pricing_policy_id: str | None = None,
        ) -> None:
            events.append(("model-loader", admin_id, default_pricing_policy_id))

        async def load_seeds_if_empty(self) -> int:
            events.append("model-loaded")
            return 2

    monkeypatch.setattr(bootstrap_model_catalog, "DataServicePricingPolicyService", _PricingService)
    monkeypatch.setattr(bootstrap_model_catalog, "DataServicePricingPolicySeedLoader", _PricingLoader)
    monkeypatch.setattr(bootstrap_model_catalog, "DataServiceModelCatalogService", _ModelService)
    monkeypatch.setattr(bootstrap_model_catalog, "DataServiceModelCatalogSeedLoader", _ModelLoader)

    loaded = await bootstrap_model_catalog.seed_model_catalog_from_env(object(), admin_id="admin@example.com")

    assert loaded == 2
    assert events[2] == "pricing-loaded"
    assert events[-2] == ("model-loader", "admin@example.com", DEFAULT_MODEL_USAGE_POLICY_KEY)
    assert events[-1] == "model-loaded"
