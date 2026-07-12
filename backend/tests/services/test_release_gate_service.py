"""Tests for release gate command runner service."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.quality.release_gate import CORE_GATE_CHECKS, EXTENDED_GATE_CHECKS
from src.services.release_gate_service import ReleaseGateCommand, ReleaseGateService


def test_release_gate_service_commands_match_evaluator_check_ids():
    service = ReleaseGateService(
        project_root=Path("/tmp/project"),
        backend_root=Path("/tmp/project/backend"),
    )

    assert tuple(command.check_id for command in service.core_commands) == CORE_GATE_CHECKS
    assert tuple(command.check_id for command in service.extended_commands) == EXTENDED_GATE_CHECKS


def test_release_gate_service_uses_configured_uv_binary(monkeypatch):
    monkeypatch.setenv("UV_BINARY", "/opt/bin/uv")

    service = ReleaseGateService(
        project_root=Path("/tmp/project"),
        backend_root=Path("/tmp/project/backend"),
    )

    assert service.uv_binary == "/opt/bin/uv"
    assert service.core_commands[0].command[0] == "/opt/bin/uv"
    assert service.extended_commands[0].command[0] == "/opt/bin/uv"


def test_release_gate_service_falls_back_to_user_local_uv(monkeypatch):
    monkeypatch.delenv("UV_BINARY", raising=False)

    with patch("src.services.release_gate_service.shutil.which", return_value=None), patch(
        "src.services.release_gate_service.Path.home",
        return_value=Path("/Users/test"),
    ), patch("src.services.release_gate_service.Path.exists", return_value=True):
        service = ReleaseGateService(
            project_root=Path("/tmp/project"),
            backend_root=Path("/tmp/project/backend"),
        )

    assert service.uv_binary == "/Users/test/.local/bin/uv"


@pytest.mark.asyncio
async def test_run_without_extended_keeps_extended_gate_pending():
    service = ReleaseGateService(
        project_root=Path("/tmp/project"),
        backend_root=Path("/tmp/project/backend"),
    )

    with patch.object(
        service,
        "_execute_checks",
        return_value=(
            {"mission_store": True, "mission_runtime": True},
            {},
        ),
    ) as mock_execute:
        report = await service.run(include_extended=False)

    assert report["status"] == "failed"
    assert report["core_gate"]["failed"] > 0  # Missing core checks still block.
    assert report["extended_gate"]["status"] == "pending"
    mock_execute.assert_called_once()


def test_execute_checks_collects_success_and_failure_details():
    service = ReleaseGateService(
        project_root=Path("/tmp/project"),
        backend_root=Path("/tmp/project/backend"),
    )
    checks = (
        ReleaseGateCommand(
            check_id="ok_check",
            command=("echo", "ok"),
            cwd=Path("/tmp/project/backend"),
        ),
        ReleaseGateCommand(
            check_id="fail_check",
            command=("echo", "fail"),
            cwd=Path("/tmp/project/backend"),
        ),
    )

    completed_ok = subprocess.CompletedProcess(
        args=["echo", "ok"],
        returncode=0,
        stdout="all good\n",
        stderr="",
    )
    completed_fail = subprocess.CompletedProcess(
        args=["echo", "fail"],
        returncode=1,
        stdout="",
        stderr="traceback\nline-2\n",
    )

    with patch(
        "src.services.release_gate_service.subprocess.run",
        side_effect=[completed_ok, completed_fail],
    ):
        results, details = service._execute_checks(checks)

    assert results == {"ok_check": True, "fail_check": False}
    assert details["ok_check"]["return_code"] == 0
    assert details["ok_check"]["output_tail"] == "all good"
    assert details["fail_check"]["return_code"] == 1
    assert "traceback" in details["fail_check"]["output_tail"]


def test_execute_checks_decodes_timeout_output_bytes():
    service = ReleaseGateService(
        project_root=Path("/tmp/project"),
        backend_root=Path("/tmp/project/backend"),
    )
    checks = (
        ReleaseGateCommand(
            check_id="timeout_check",
            command=("echo", "slow"),
            cwd=Path("/tmp/project/backend"),
        ),
    )
    timeout = subprocess.TimeoutExpired(
        cmd=["echo", "slow"],
        timeout=1,
        output=b"partial stdout\n",
        stderr=b"partial stderr\n",
    )

    with patch(
        "src.services.release_gate_service.subprocess.run",
        side_effect=timeout,
    ):
        results, details = service._execute_checks(checks)

    assert results == {"timeout_check": False}
    assert details["timeout_check"]["error"] == "timeout after 600s"
    assert "partial stdout" in details["timeout_check"]["output_tail"]
    assert "partial stderr" in details["timeout_check"]["output_tail"]
    assert "b'partial" not in details["timeout_check"]["output_tail"]
