"""Tests for Prometheus metrics integration."""

import os
from tempfile import TemporaryDirectory
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


class TestWorkerPrometheus:
    def test_prepare_worker_prometheus_resets_multiproc_dir(self):
        import src.observability.prometheus as prom

        with TemporaryDirectory() as tmpdir:
            stale_file = os.path.join(tmpdir, "stale.db")
            with open(stale_file, "w", encoding="utf-8") as handle:
                handle.write("stale")

            saved_env = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
            try:
                with patch("src.observability.prometheus.get_prometheus_settings") as mock:
                    mock.return_value = MagicMock(
                        enabled=True,
                        worker_port=9153,
                        multiproc_dir=tmpdir,
                    )
                    prom.prepare_worker_prometheus()

                assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == tmpdir
                assert os.path.isdir(tmpdir)
                assert not os.listdir(tmpdir)
            finally:
                if saved_env is None:
                    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
                else:
                    os.environ["PROMETHEUS_MULTIPROC_DIR"] = saved_env

    def test_start_worker_prometheus_server_is_idempotent(self):
        import src.observability.prometheus as prom

        saved_started = prom._worker_metrics_server_started
        prom._worker_metrics_server_started = False
        try:
            with patch("src.observability.prometheus.get_prometheus_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    enabled=True,
                    worker_port=9153,
                    multiproc_dir="",
                )
                with patch(
                    "src.observability.prometheus._build_metrics_registry",
                    return_value=object(),
                ):
                    with patch("prometheus_client.start_http_server") as mock_start:
                        prom.start_worker_prometheus_server()
                        prom.start_worker_prometheus_server()

            mock_start.assert_called_once()
        finally:
            prom._worker_metrics_server_started = saved_started
