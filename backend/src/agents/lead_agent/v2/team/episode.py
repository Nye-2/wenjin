"""Bounded TeamKernel episode projection for recruitment/replan audits."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import QualityGateResult

HARNESS_EPISODE_SCHEMA = "wenjin.team.harness_episode.v1"


def start_harness_episode(
    *,
    execution_id: str,
    core_templates: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": HARNESS_EPISODE_SCHEMA,
        "execution_id": str(execution_id or ""),
        "status": "running",
        "core_templates": [str(item) for item in core_templates if str(item or "").strip()],
        "decisions": [],
        "stop_reason": "",
    }


def record_replan_decision(
    episode: dict[str, Any],
    *,
    iteration: int,
    phase: str,
    gates: Sequence[QualityGateResult],
    selected_recruits: Sequence[str],
) -> None:
    decisions = episode.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
        episode["decisions"] = decisions
    selected = [str(item) for item in selected_recruits if str(item or "").strip()]
    decisions.append(
        {
            "schema": "wenjin.team.harness_replan_decision.v1",
            "iteration": int(iteration),
            "phase": str(phase or ""),
            "gate_ids": _gate_ids(gates),
            "gate_statuses": _gate_statuses(gates),
            "next_action": _dominant_next_action(gates),
            "selected_recruits": selected,
        }
    )


def finish_harness_episode(episode: dict[str, Any], *, stop_reason: str) -> None:
    episode["status"] = "finished"
    episode["stop_reason"] = str(stop_reason or "unknown")


def stop_reason_from_gates(gates: Sequence[QualityGateResult], *, selected_recruits: Sequence[str]) -> str:
    if selected_recruits:
        return ""
    if any(gate.next_action == "ask_user" for gate in gates):
        return "awaiting_user"
    if any(gate.next_action == "stop_with_warning" for gate in gates):
        return "stopped_with_warning"
    if any(gate.status == "fail" for gate in gates):
        return "blocked_without_recruit"
    return "quality_gates_satisfied"


def bounded_harness_episode(episode: dict[str, Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    raw_decisions = episode.get("decisions")
    raw_decisions = raw_decisions if isinstance(raw_decisions, list) else []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        decisions.append(
            {
                "schema": str(item.get("schema") or "wenjin.team.harness_replan_decision.v1"),
                "iteration": _int_value(item.get("iteration")),
                "phase": str(item.get("phase") or ""),
                "gate_ids": _string_list(item.get("gate_ids")),
                "gate_statuses": _string_list(item.get("gate_statuses")),
                "next_action": str(item.get("next_action") or ""),
                "selected_recruits": _string_list(item.get("selected_recruits")),
            }
        )
    return {
        "schema": HARNESS_EPISODE_SCHEMA,
        "execution_id": str(episode.get("execution_id") or ""),
        "status": str(episode.get("status") or "running"),
        "core_templates": _string_list(episode.get("core_templates")),
        "decisions": decisions[:12],
        "stop_reason": str(episode.get("stop_reason") or ""),
    }


def _dominant_next_action(gates: Sequence[QualityGateResult]) -> str:
    order = ("ask_user", "stop_with_warning", "recruit_more", "revise_existing", "finish")
    actions = {gate.next_action for gate in gates}
    for action in order:
        if action in actions:
            return action
    return "finish"


def _gate_ids(gates: Sequence[QualityGateResult]) -> list[str]:
    return _dedupe([gate.gate_id for gate in gates])


def _gate_statuses(gates: Sequence[QualityGateResult]) -> list[str]:
    return _dedupe([f"{gate.gate_id}:{gate.status}" for gate in gates])


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list | tuple) else [value]
    return _dedupe([str(item).strip() for item in raw if str(item or "").strip()])


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
