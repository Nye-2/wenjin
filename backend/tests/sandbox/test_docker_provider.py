"""Tests for Docker sandbox provider."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.sandbox.providers.docker import DockerSandboxProvider


class _FakeDockerClient:
    def __init__(self) -> None:
        self.ensure_image = AsyncMock(return_value=True)
        self.run_container = AsyncMock(return_value=(0, "ok", ""))
        self.cleanup_containers_by_label = AsyncMock(return_value=0)

    @staticmethod
    def build_volume_mapping(host_path: str, container_path: str, mode: str = "rw"):
        return {
            host_path: {
                "bind": container_path,
                "mode": mode,
            }
        }


@pytest.mark.asyncio
async def test_docker_provider_acquire_creates_thread_directories(tmp_path):
    docker_client = _FakeDockerClient()
    provider = DockerSandboxProvider(
        base_dir=str(tmp_path),
        image="wenjin/sandbox:test",
        docker_client=docker_client,
    )

    sandbox = await provider.acquire("thread-1")

    assert sandbox.sandbox_id == "thread-1"
    assert (tmp_path / "thread-1" / "user-data" / "workspace").exists()
    assert (tmp_path / "thread-1" / "user-data" / "uploads").exists()
    assert (tmp_path / "thread-1" / "user-data" / "outputs").exists()
    docker_client.cleanup_containers_by_label.assert_awaited_once()
    docker_client.ensure_image.assert_awaited_once_with("wenjin/sandbox:test")


@pytest.mark.asyncio
async def test_docker_sandbox_executes_command_in_ephemeral_container(tmp_path):
    docker_client = _FakeDockerClient()
    provider = DockerSandboxProvider(
        base_dir=str(tmp_path),
        image="wenjin/sandbox:test",
        memory="512m",
        cpu_limit=1,
        docker_client=docker_client,
    )
    sandbox = await provider.acquire("thread-2")

    result = await sandbox.execute_command("pwd", timeout=45)

    assert result.success
    docker_client.run_container.assert_awaited_once()
    kwargs = docker_client.run_container.await_args.kwargs
    assert kwargs["image"] == "wenjin/sandbox:test"
    assert kwargs["command"] == ["/bin/sh", "-lc", "pwd"]
    assert kwargs["working_dir"] == "/mnt/user-data/workspace"
    assert kwargs["timeout"] == 45
    assert kwargs["network_disabled"] is True
    assert kwargs["mem_limit"] == "512m"
    assert kwargs["labels"]["wenjin.sandbox.managed"] == "true"
    assert kwargs["labels"]["wenjin.sandbox.kind"] == "sandbox_exec"
    assert kwargs["labels"]["wenjin.sandbox.thread_id"] == "thread-2"


@pytest.mark.asyncio
async def test_docker_provider_reconcile_runs_only_once(tmp_path):
    docker_client = _FakeDockerClient()
    provider = DockerSandboxProvider(
        base_dir=str(tmp_path),
        image="wenjin/sandbox:test",
        docker_client=docker_client,
    )

    await provider.acquire("thread-a")
    await provider.acquire("thread-b")

    docker_client.cleanup_containers_by_label.assert_awaited_once()
