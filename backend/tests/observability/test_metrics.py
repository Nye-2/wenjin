"""Tests for Task 1.18 observability metrics — spec §4.5.4.

The /metrics endpoint is provided by src.observability.prometheus (existing).
Our new src.observability.metrics module registers additional prometheus
counters / histograms into the default REGISTRY.  This test verifies that
those metric names appear in the /metrics output.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    """Minimal FastAPI app with Prometheus enabled at /metrics."""
    app = FastAPI()

    with patch("src.observability.prometheus.get_prometheus_settings") as mock_settings:
        mock_settings.return_value = MagicMock(enabled=True, multiproc_dir="")

        # Import metrics module so all new metric objects are registered
        import src.observability.metrics  # noqa: F401
        from src.observability.prometheus import setup_prometheus

        setup_prometheus(app)

    return TestClient(app)


def test_metrics_endpoint_exposes_keys(client: TestClient) -> None:
    """The /metrics endpoint exposes our key metric names."""
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "mission_stream_latency_seconds" in body
    assert "workspace_agent_response_latency_seconds" in body
    assert "mission_slice_duration_seconds" in body
    assert "auto_compact_trigger_total" in body


def test_tracing_noop_tracer_is_usable() -> None:
    """The V1 no-op tracer can be used as a context manager without errors."""
    from src.observability.tracing import tracer

    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("key", "value")
        span.add_event("test-event")
