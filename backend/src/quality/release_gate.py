"""Strict Mission architecture release-gate contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

CORE_GATE_CHECKS: tuple[str, ...] = (
    "mission_store",
    "mission_runtime",
    "mission_catalog",
    "workspace_agent",
    "subagent_runtime",
    "tool_orchestrator",
    "model_capability",
    "sandbox_security",
    "review_commit",
    "mission_cutover",
    "frontend_mission",
    "frontend_typecheck",
)

EXTENDED_GATE_CHECKS: tuple[str, ...] = (
    "backend_full_suite",
    "frontend_build",
    "mission_browser_e2e",
)

CHECK_DESCRIPTIONS: Mapping[str, str] = {
    "mission_store": "Mission schema, store, lease, immutable ledger, and client contracts.",
    "mission_runtime": "Bounded Mission slices, reconciliation, fencing, and worker delivery.",
    "mission_catalog": "All workspace policies and pinned WorkerSkills are seeded, versioned, and cross-referenced.",
    "workspace_agent": "Structured WorkspaceAgent routing and ChatTurnRun transport.",
    "subagent_runtime": "Bounded isolated subagent jobs and MissionItem lifecycle.",
    "tool_orchestrator": "Typed tool catalog, operation identity, receipts, and policy.",
    "model_capability": "Versioned model probes and receipt-backed model-native search.",
    "sandbox_security": "Hardened operation containers, manifests, and path/network controls.",
    "review_commit": "MissionReviewItem decisions and atomic MissionCommit materialization.",
    "mission_cutover": "Strict production-source scan for retired runtime paths.",
    "frontend_mission": "MissionView, Mission Console, review, and UI state unit contracts.",
    "frontend_typecheck": "Frontend TypeScript contract check.",
    "backend_full_suite": "Full backend test suite.",
    "frontend_build": "Frontend production build.",
    "mission_browser_e2e": "Browser main-chain Mission Console scenario.",
}

CHECK_FIX_HINTS: Mapping[str, str] = {check_id: f"Run the configured {check_id} command and resolve every failure." for check_id in (*CORE_GATE_CHECKS, *EXTENDED_GATE_CHECKS)}


def _evaluate_gate(
    check_ids: tuple[str, ...],
    results: Mapping[str, bool] | None,
    *,
    missing_as_failed: bool,
) -> dict[str, Any]:
    normalized = results or {}
    checks: list[dict[str, str]] = []
    passed = failed = missing = 0
    for check_id in check_ids:
        value = normalized.get(check_id)
        if value is True:
            status = "passed"
            passed += 1
        elif value is False:
            status = "failed"
            failed += 1
        else:
            status = "missing"
            missing += 1
            if missing_as_failed:
                failed += 1
        checks.append(
            {
                "id": check_id,
                "status": status,
                "description": CHECK_DESCRIPTIONS[check_id],
                "fix_hint": CHECK_FIX_HINTS[check_id],
            }
        )
    status = "failed" if failed else ("pending" if missing else "passed")
    return {
        "status": status,
        "total": len(check_ids),
        "passed": passed,
        "failed": failed,
        "missing": missing,
        "checks": checks,
    }


def evaluate_release_gate(
    *,
    core_results: Mapping[str, bool],
    extended_results: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Return strict core readiness plus advisory extended checks."""
    core_gate = _evaluate_gate(CORE_GATE_CHECKS, core_results, missing_as_failed=True)
    extended_gate = _evaluate_gate(
        EXTENDED_GATE_CHECKS,
        extended_results,
        missing_as_failed=False,
    )
    recommendations = [f"[core] {item['id']}: {item['fix_hint']}" for item in core_gate["checks"] if item["status"] in {"failed", "missing"}]
    recommendations.extend(f"[extended] {item['id']}: {item['fix_hint']}" for item in extended_gate["checks"] if item["status"] == "failed")
    if extended_gate["status"] == "pending":
        recommendations.append("[extended] Run extended checks before deployment.")
    passed = core_gate["status"] == "passed"
    return {
        "status": "passed" if passed else "failed",
        "go_no_go": "go" if passed else "no-go",
        "core_gate": core_gate,
        "extended_gate": extended_gate,
        "generated_at": datetime.now(UTC).isoformat(),
        "recommendations": recommendations,
    }
