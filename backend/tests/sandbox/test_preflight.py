from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

from src.sandbox.preflight import (
    docker_socket_access_check,
    exec_process,
    sandbox_free_environment,
    workspace_policy_checks,
)


def test_docker_socket_access_check_accepts_accessible_unix_socket() -> None:
    with tempfile.TemporaryDirectory(prefix="wjn-", dir="/tmp") as temporary:
        path = Path(temporary) / "docker.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        try:
            check = docker_socket_access_check(docker_host=f"unix://{path}")
        finally:
            server.close()

    assert check.passed
    assert "uid=" in check.detail
    assert "gid=" in check.detail


def test_docker_socket_access_check_rejects_remote_endpoint() -> None:
    check = docker_socket_access_check(docker_host="tcp://docker.example:2376")

    assert not check.passed
    assert "remote Docker endpoints are forbidden" in check.detail


def test_docker_socket_access_check_reports_group_remediation(monkeypatch) -> None:
    monkeypatch.setattr(os, "access", lambda *_args, **_kwargs: False)
    with tempfile.TemporaryDirectory(prefix="wjn-", dir="/tmp") as temporary:
        path = Path(temporary) / "docker.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        try:
            check = docker_socket_access_check(docker_host=f"unix://{path}")
        finally:
            server.close()

    assert not check.passed
    assert "container-visible mounted socket gid" in check.detail


def test_workspace_policy_checks_exercises_read_before_write(tmp_path) -> None:
    checks = workspace_policy_checks(tmp_path / "sandbox")

    assert {check.name for check in checks} == {"workspace_access", "read_before_write"}
    assert all(check.passed for check in checks)
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_sandbox_free_environment_removes_the_entire_prefix() -> None:
    environment = sandbox_free_environment(
        {
            "PATH": "/usr/bin",
            "SANDBOX_PROVIDER": "docker",
            "sandbox_docker__image": "private",
        }
    )

    assert environment == {"PATH": "/usr/bin"}


def test_exec_process_preserves_argv_and_uses_supplied_environment(monkeypatch) -> None:
    captured = {}

    def fake_execvpe(file, args, environment):
        captured.update(file=file, args=args, environment=environment)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(os, "execvpe", fake_execvpe)

    with pytest.raises(RuntimeError, match="exec intercepted"):
        exec_process(("python", "-m", "worker"), environment={"PATH": "/bin"})

    assert captured == {
        "file": "python",
        "args": ["python", "-m", "worker"],
        "environment": {"PATH": "/bin"},
    }
