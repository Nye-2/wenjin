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

    def test_track_run_noop_when_not_initialized(self):
        """Run metrics helpers should not raise when metrics are None."""
        import src.observability.prometheus as prom

        saved_dispatch = prom._run_dispatch_total
        saved_wait_seconds = prom._run_wait_seconds
        saved_wait_polls = prom._run_wait_polls
        prom._run_dispatch_total = None
        prom._run_wait_seconds = None
        prom._run_wait_polls = None
        try:
            prom.track_run_dispatch("success")
            prom.observe_run_wait("success", 0.12, 3)
        finally:
            prom._run_dispatch_total = saved_dispatch
            prom._run_wait_seconds = saved_wait_seconds
            prom._run_wait_polls = saved_wait_polls

    def test_mission_metrics_use_bounded_operational_labels(self):
        import src.observability.prometheus as prom

        saved = (
            prom._mission_queue_wait_seconds,
            prom._mission_slice_duration_seconds,
            prom._mission_slices_total,
            prom._mission_lease_events_total,
            prom._mission_dispatch_events_total,
            prom._mission_reconciliation_total,
            prom._mission_subagent_capacity_total,
        )
        queue_wait = MagicMock()
        slice_duration = MagicMock()
        slices = MagicMock()
        leases = MagicMock()
        dispatch = MagicMock()
        reconciliation = MagicMock()
        capacity = MagicMock()
        (
            prom._mission_queue_wait_seconds,
            prom._mission_slice_duration_seconds,
            prom._mission_slices_total,
            prom._mission_lease_events_total,
            prom._mission_dispatch_events_total,
            prom._mission_reconciliation_total,
            prom._mission_subagent_capacity_total,
        ) = (
            queue_wait,
            slice_duration,
            slices,
            leases,
            dispatch,
            reconciliation,
            capacity,
        )
        try:
            prom.observe_mission_queue_wait(2.5)
            prom.track_mission_slice(
                outcome="yielded",
                reason="lease_fence_lost",
                duration=1.25,
            )
            prom.track_mission_dispatch("published")
            prom.track_mission_reconciliation("published")
            prom.track_mission_subagent_capacity("acquired")
        finally:
            (
                prom._mission_queue_wait_seconds,
                prom._mission_slice_duration_seconds,
                prom._mission_slices_total,
                prom._mission_lease_events_total,
                prom._mission_dispatch_events_total,
                prom._mission_reconciliation_total,
                prom._mission_subagent_capacity_total,
            ) = saved

        queue_wait.observe.assert_called_once_with(2.5)
        slice_duration.labels.assert_called_once_with(outcome="yielded")
        slices.labels.assert_called_once_with(
            outcome="yielded",
            reason="lease_fence_lost",
        )
        leases.labels.assert_called_once_with(result="lease_fence_lost")
        dispatch.labels.assert_called_once_with(result="published")
        reconciliation.labels.assert_called_once_with(result="published")
        capacity.labels.assert_called_once_with(result="acquired")


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

                assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == os.path.realpath(tmpdir)
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
