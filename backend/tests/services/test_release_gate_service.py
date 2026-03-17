"""Tests for release gate command runner service."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.release_gate_service import ReleaseGateCommand, ReleaseGateService


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
            {"thesis_output_language_zh": True, "sci_output_language_en": True},
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

