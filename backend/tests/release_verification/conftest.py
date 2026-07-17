"""Disposable PostgreSQL infrastructure for release verification."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REQUIRE_ENV = "WENJIN_REQUIRE_POSTGRES_RELEASE_VERIFICATION"
IMAGE_ENV = "WENJIN_POSTGRES_VERIFICATION_IMAGE"
DEFAULT_IMAGE = "pgvector/pgvector:pg16"


@dataclass(frozen=True, slots=True)
class PostgresReleaseDatabase:
    """Connection details for one empty database migrated to revision 107."""

    async_url: str
    container_name: str
    database_name: str


def _required() -> bool:
    return os.getenv(REQUIRE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _infrastructure_unavailable(reason: str) -> NoReturn:
    message = f"PostgreSQL release verification infrastructure unavailable: {reason}"
    if _required():
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message}; set {REQUIRE_ENV}=1 to make this a release-blocking failure")


def _container_logs(container: Any) -> str:
    try:
        raw = container.logs(tail=200)
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        return f"unable to read container logs: {exc}"
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _wait_for_postgres(container: Any, *, database_name: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        container.reload()
        if container.status in {"dead", "exited"}:
            pytest.fail(
                "Disposable PostgreSQL exited before becoming ready:\n"
                + _container_logs(container),
                pytrace=False,
            )
        probe = container.exec_run(
            ["pg_isready", "-U", "postgres", "-d", database_name],
        )
        if probe.exit_code == 0:
            return
        time.sleep(0.25)
    pytest.fail(
        "Disposable PostgreSQL did not become ready within 45 seconds:\n"
        + _container_logs(container),
        pytrace=False,
    )


def _host_port(container: Any) -> int:
    container.reload()
    bindings = container.attrs["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if len(bindings) != 1:
        pytest.fail(
            f"Expected one loopback PostgreSQL port binding, found {bindings!r}",
            pytrace=False,
        )
    binding = bindings[0]
    if binding.get("HostIp") != "127.0.0.1":
        pytest.fail(
            f"Disposable PostgreSQL was not bound to loopback: {binding!r}",
            pytrace=False,
        )
    return int(binding["HostPort"])


def _upgrade_empty_database(async_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = async_url
    env["PYTHONUNBUFFERED"] = "1"
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "107_runtime_accounting",
            ],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"Alembic did not upgrade the empty PostgreSQL database within 240 seconds: {exc}",
            pytrace=False,
        )
    if result.returncode != 0:
        pytest.fail(
            "Alembic failed to upgrade the empty PostgreSQL database to "
            "107_runtime_accounting.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def postgres_107_database() -> Iterator[PostgresReleaseDatabase]:
    """Start a private PostgreSQL container and migrate its empty database."""

    try:
        from docker.errors import DockerException, ImageNotFound

        import docker
    except ImportError as exc:  # pragma: no cover - docker is a project dependency
        _infrastructure_unavailable(f"Python Docker SDK is not installed ({exc})")

    client = None
    container = None
    try:
        try:
            client = docker.from_env(timeout=5)
            client.ping()
        except DockerException as exc:
            _infrastructure_unavailable(f"Docker daemon is not reachable ({exc})")

        image = os.getenv(IMAGE_ENV, DEFAULT_IMAGE).strip() or DEFAULT_IMAGE
        try:
            client.images.get(image)
        except ImageNotFound:
            if not _required():
                _infrastructure_unavailable(
                    f"Docker image {image!r} is not present locally"
                )
            try:
                client.images.pull(image)
            except DockerException as exc:
                _infrastructure_unavailable(
                    f"Docker image {image!r} could not be pulled ({exc})"
                )

        suffix = secrets.token_hex(8)
        password = secrets.token_hex(24)
        database_name = f"wenjin_runtime_accounting_{suffix}"
        container_name = f"wenjin-runtime-accounting-{suffix}"
        try:
            container = client.containers.run(
                image,
                detach=True,
                name=container_name,
                environment={
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": database_name,
                },
                labels={
                    "wenjin.release-verification": "runtime-accounting",
                },
                ports={"5432/tcp": ("127.0.0.1", None)},
            )
        except DockerException as exc:
            _infrastructure_unavailable(
                f"Disposable PostgreSQL container could not start ({exc})"
            )

        _wait_for_postgres(container, database_name=database_name)
        port = _host_port(container)
        async_url = (
            f"postgresql+asyncpg://postgres:{password}@127.0.0.1:{port}/"
            f"{database_name}"
        )
        _upgrade_empty_database(async_url)

        yield PostgresReleaseDatabase(
            async_url=async_url,
            container_name=container_name,
            database_name=database_name,
        )
    finally:
        cleanup_error: Exception | None = None
        if container is not None:
            try:
                container.remove(force=True, v=True)
            except Exception as exc:  # pragma: no cover - daemon teardown failure
                cleanup_error = exc
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if cleanup_error is not None:
            pytest.fail(
                "Failed to remove the disposable PostgreSQL container and data "
                f"volume: {cleanup_error}",
                pytrace=False,
            )
