"""Tests for execution capability checks."""

from __future__ import annotations

from src.execution.capabilities import execution_type_readiness
from src.execution.types import ExecutionType


class _Service:
    def __init__(self, provider_map):
        self.PROVIDER_MAP = provider_map


def test_readiness_false_when_provider_not_registered():
    service = _Service({ExecutionType.MERMAID_DIAGRAM: object})
    ready, reason = execution_type_readiness(service, ExecutionType.AI_IMAGE)
    assert ready is False
    assert "not registered" in str(reason)


def test_readiness_true_for_non_ai_type_when_registered():
    service = _Service({ExecutionType.MERMAID_DIAGRAM: object})
    ready, reason = execution_type_readiness(service, ExecutionType.MERMAID_DIAGRAM)
    assert ready is True
    assert reason is None


def test_ai_readiness_false_when_model_routing_fails(monkeypatch):
    service = _Service({ExecutionType.AI_IMAGE: object})

    def _raise(**kwargs):
        _ = kwargs
        raise ValueError("no image model")

    monkeypatch.setattr("src.execution.capabilities.route_image_model", _raise)
    ready, reason = execution_type_readiness(service, ExecutionType.AI_IMAGE)
    assert ready is False
    assert "image model unavailable" in str(reason)


def test_ai_readiness_false_when_config_incomplete(monkeypatch):
    service = _Service({ExecutionType.AI_IMAGE: object})

    monkeypatch.setattr(
        "src.execution.capabilities.route_image_model",
        lambda **kwargs: "img-model",
    )
    monkeypatch.setattr(
        "src.execution.capabilities.get_model_full_config",
        lambda _model_id: {"base_url": "", "api_key": "x", "model": "y"},
    )
    ready, reason = execution_type_readiness(service, ExecutionType.AI_IMAGE)
    assert ready is False
    assert "missing" in str(reason)


def test_ai_readiness_true_when_config_complete(monkeypatch):
    service = _Service({ExecutionType.AI_IMAGE: object})

    monkeypatch.setattr(
        "src.execution.capabilities.route_image_model",
        lambda **kwargs: "img-model",
    )
    monkeypatch.setattr(
        "src.execution.capabilities.get_model_full_config",
        lambda _model_id: {
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "image-model",
        },
    )
    ready, reason = execution_type_readiness(service, ExecutionType.AI_IMAGE)
    assert ready is True
    assert reason is None

