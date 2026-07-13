"""Deployment topology contracts for Celery Mission recovery."""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _compose(filename: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / filename).read_text(encoding="utf-8"))


def test_compose_runs_one_healthy_celery_beat_scheduler() -> None:
    services = _compose("docker-compose.yml")["services"]
    beat = services["celery-beat"]
    beat_command = " ".join(beat["command"])

    assert "exec celery -A src.task.celery_app beat" in beat_command
    assert "rm -f /tmp/celerybeat.pid" in beat_command
    assert "--pidfile=/tmp/celerybeat.pid" in beat_command
    assert "kill -0" in beat["healthcheck"]["test"][1]
    assert services["gateway"]["depends_on"]["celery-beat"]["condition"] == "service_healthy"


def test_mission_worker_health_requires_validated_gpt56_default_profile() -> None:
    mission_worker = _compose("docker-compose.yml")["services"]["mission-worker"]

    assert "--require-mission-model-profile" in mission_worker["command"]
    health_command = mission_worker["healthcheck"]["test"][1]
    assert "gpt-5\\.6-(sol|terra|luna)" in health_command
    assert "/tmp/wenjin-worker-ready" in health_command
    assert "/metrics" in health_command


def test_local_build_override_builds_scheduler_and_keeps_strict_mission_bootstrap() -> None:
    services = _compose("docker-compose.local-build.yml")["services"]

    assert "build" in services["celery-beat"]
    assert "--require-mission-model-profile" in services["mission-worker"]["command"]
