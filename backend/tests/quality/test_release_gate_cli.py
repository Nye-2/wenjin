"""Tests for release gate CLI wrapper."""

from unittest.mock import AsyncMock, patch

from src.quality.release_gate_cli import main


def test_release_gate_cli_returns_zero_when_passed():
    with patch("src.quality.release_gate_cli.ReleaseGateService") as mock_service_cls:
        service = mock_service_cls.return_value
        service.run = AsyncMock(return_value={"status": "passed", "go_no_go": "go"})

        exit_code = main(["--include-extended"])

    assert exit_code == 0
    service.run.assert_awaited_once_with(include_extended=True)


def test_release_gate_cli_returns_one_when_failed():
    with patch("src.quality.release_gate_cli.ReleaseGateService") as mock_service_cls:
        service = mock_service_cls.return_value
        service.run = AsyncMock(return_value={"status": "failed", "go_no_go": "no-go"})

        exit_code = main([])

    assert exit_code == 1
    service.run.assert_awaited_once_with(include_extended=False)

