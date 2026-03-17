"""Tests for Prometheus metrics integration."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSetupPrometheus:
    def test_skips_when_disabled(self):
        app = FastAPI()
        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=False)
            from src.observability.prometheus import setup_prometheus

            setup_prometheus(app)
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_metrics_endpoint_available_when_enabled(self):
        app = FastAPI()
        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=True)
            from src.observability.prometheus import setup_prometheus

            setup_prometheus(app)
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_http_metrics_collected(self):
        app = FastAPI()

        @app.get("/test-route")
        async def test_route():
            return {"ok": True}

        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=True)
            from src.observability.prometheus import setup_prometheus

            setup_prometheus(app)

        client = TestClient(app)
        client.get("/test-route")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text


class TestTaskMetrics:
    def test_track_task_noop_when_not_initialized(self):
        """track_task_start/end should not raise when metrics are None."""
        import src.observability.prometheus as prom

        # Save and reset
        saved_gauge = prom._active_tasks_gauge
        saved_hist = prom._task_duration_seconds
        prom._active_tasks_gauge = None
        prom._task_duration_seconds = None
        try:
            prom.track_task_start()
            prom.track_task_end("test", 1.0)
        finally:
            prom._active_tasks_gauge = saved_gauge
            prom._task_duration_seconds = saved_hist
