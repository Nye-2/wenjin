"""Tests for model catalog and pricing release-gate readiness."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.quality.model_catalog_pricing_gate import (
    evaluate_dataservice_model_catalog_pricing_gate,
    evaluate_model_catalog_pricing_gate,
)


def _model(**overrides):
    data = {
        "model_id": "deepseek-chat",
        "category": "llm",
        "enabled": True,
        "is_default": True,
        "health_status": "healthy",
        "pricing_policy_id": "deepseek-chat-policy",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _policy(policy_kind: str, policy_key: str, **overrides):
    data = {
        "id": policy_key,
        "policy_key": policy_key,
        "policy_kind": policy_kind,
        "enabled": True,
        "config": {},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_model_catalog_pricing_gate_passes_for_ready_catalog() -> None:
    report = evaluate_model_catalog_pricing_gate(
        models=[_model()],
        pricing_policies=[
            _policy("global_credit", "global-credit"),
            _policy("model_usage", "deepseek-chat-policy"),
            _policy("mission", "thesis-default", config={"workspace_type": "thesis"}),
            _policy("sandbox", "sandbox-default"),
        ],
        mission_policies=[SimpleNamespace(id="thesis_research_pack", workspace_type="thesis", enabled=True, tier="primary")],
        sandbox_enabled=True,
        env={"MODEL_SECRET_KEY": "x" * 32, "WENJIN_SANDBOX_ENABLED": "true"},
    )

    assert report == {"status": "passed", "errors": []}


def test_model_catalog_pricing_gate_fails_without_enabled_default_llm_model() -> None:
    report = evaluate_model_catalog_pricing_gate(
        models=[_model(is_default=False)],
        pricing_policies=[
            _policy("global_credit", "global-credit"),
            _policy("model_usage", "deepseek-chat-policy"),
        ],
        env={"MODEL_SECRET_KEY": "x" * 32},
    )

    assert report["status"] == "failed"
    assert "enabled_default_llm_model_missing" in {error["code"] for error in report["errors"]}


def test_model_catalog_pricing_gate_rejects_all_zero_model_secret_placeholder() -> None:
    report = evaluate_model_catalog_pricing_gate(
        models=[_model()],
        pricing_policies=[
            _policy("global_credit", "global-credit"),
            _policy("model_usage", "deepseek-chat-policy"),
        ],
        env={"MODEL_SECRET_KEY": "base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="},
    )

    assert report["status"] == "failed"
    assert "model_secret_key_missing" in {error["code"] for error in report["errors"]}


def test_model_catalog_pricing_gate_fails_when_enabled_model_lacks_pricing_policy() -> None:
    report = evaluate_model_catalog_pricing_gate(
        models=[_model(pricing_policy_id=None)],
        pricing_policies=[_policy("global_credit", "global-credit")],
        env={"MODEL_SECRET_KEY_FILE": "/run/secrets/model_key"},
    )

    assert report["status"] == "failed"
    assert "model_usage_policy_missing" in {error["code"] for error in report["errors"]}


def test_model_catalog_pricing_gate_fails_when_default_model_is_not_healthy() -> None:
    report = evaluate_model_catalog_pricing_gate(
        models=[_model(health_status="unknown")],
        pricing_policies=[
            _policy("global_credit", "global-credit"),
            _policy("model_usage", "deepseek-chat-policy"),
        ],
        env={"MODEL_SECRET_KEY": "x" * 32},
    )

    assert report["status"] == "failed"
    assert "default_model_health_check_missing" in {error["code"] for error in report["errors"]}


@pytest.mark.asyncio
async def test_dataservice_gate_reads_mission_policy_catalog() -> None:
    dataservice = SimpleNamespace(
        list_model_catalog_models=AsyncMock(return_value=[_model()]),
        list_pricing_policies=AsyncMock(
            return_value=[
                _policy("global_credit", "global-credit"),
                _policy("model_usage", "deepseek-chat-policy"),
                _policy("mission", "sci-default", config={"workspace_type": "sci"}),
            ]
        ),
        list_mission_policies=AsyncMock(return_value=[SimpleNamespace(id="sci_research", workspace_type="sci", enabled=True)]),
    )

    report = await evaluate_dataservice_model_catalog_pricing_gate(
        dataservice=dataservice,
        env={"MODEL_SECRET_KEY": "x" * 32},
    )

    assert report["status"] == "passed"
    dataservice.list_mission_policies.assert_awaited_once_with(enabled_only=True)
