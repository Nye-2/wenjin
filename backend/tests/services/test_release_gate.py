"""Tests for release gate evaluation."""

from src.quality.release_gate import (
    CORE_GATE_CHECKS,
    EXTENDED_GATE_CHECKS,
    evaluate_release_gate,
)


def _all_core_passed() -> dict[str, bool]:
    return {check: True for check in CORE_GATE_CHECKS}


def _all_extended_passed() -> dict[str, bool]:
    return {check: True for check in EXTENDED_GATE_CHECKS}


def test_release_gate_fails_when_core_check_missing():
    core_results = _all_core_passed()
    core_results.pop(CORE_GATE_CHECKS[0])

    report = evaluate_release_gate(core_results=core_results)

    assert report["status"] == "failed"
    assert report["go_no_go"] == "no-go"
    assert report["core_gate"]["status"] == "failed"

    checks = {item["id"]: item for item in report["core_gate"]["checks"]}
    assert checks[CORE_GATE_CHECKS[0]]["status"] == "missing"
    assert report["core_gate"]["failed"] == 1
    assert report["recommendations"]


def test_release_gate_passes_when_core_gate_passed_even_if_extended_not_run():
    report = evaluate_release_gate(core_results=_all_core_passed())

    assert report["status"] == "passed"
    assert report["go_no_go"] == "go"
    assert report["core_gate"]["status"] == "passed"
    assert report["core_gate"]["passed"] == len(CORE_GATE_CHECKS)
    assert report["extended_gate"]["status"] == "pending"
    assert report["extended_gate"]["missing"] == len(EXTENDED_GATE_CHECKS)


def test_release_gate_keeps_core_go_when_extended_gate_failed():
    extended_results = _all_extended_passed()
    extended_results["backend_full_suite"] = False

    report = evaluate_release_gate(
        core_results=_all_core_passed(),
        extended_results=extended_results,
    )

    assert report["status"] == "passed"
    assert report["go_no_go"] == "go"
    assert report["core_gate"]["status"] == "passed"
    assert report["extended_gate"]["status"] == "failed"
    assert report["extended_gate"]["failed"] == 1
    assert any("backend_full_suite" in item for item in report["recommendations"])
