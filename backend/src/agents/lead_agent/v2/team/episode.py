"""Bounded TeamKernel episode projection for recruitment/replan audits."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import HarnessEpisode, HarnessReplanDecision, QualityGateResult

HARNESS_EPISODE_SCHEMA = "wenjin.team.harness_episode.v1"


def start_harness_episode(
    *,
    execution_id: str,
    core_templates: Sequence[str],
) -> HarnessEpisode:
    return HarnessEpisode(
        execution_id=str(execution_id or ""),
        core_templates=[str(item) for item in core_templates if str(item or "").strip()],
    )


def record_replan_decision(
    episode: HarnessEpisode,
    *,
    iteration: int,
    phase: str,
    gates: Sequence[QualityGateResult],
    selected_recruits: Sequence[str],
) -> None:
    selected = [str(item) for item in selected_recruits if str(item or "").strip()]
    episode.decisions.append(
        HarnessReplanDecision(
            iteration=int(iteration),
            phase=str(phase or ""),
            gate_ids=_gate_ids(gates),
            gate_statuses=_gate_statuses(gates),
            next_action=_dominant_next_action(gates),
            selected_recruits=selected,
        )
    )


def finish_harness_episode(episode: HarnessEpisode, *, stop_reason: str) -> None:
    episode.status = "finished"
    episode.stop_reason = str(stop_reason or "unknown")


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


def bounded_harness_episode(episode: HarnessEpisode) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for item in episode.decisions:
        decisions.append(
            {
                "schema": item.schema_id,
                "iteration": _int_value(item.iteration),
                "phase": item.phase,
                "gate_ids": _string_list(item.gate_ids),
                "gate_statuses": _string_list(item.gate_statuses),
                "next_action": item.next_action,
                "selected_recruits": _string_list(item.selected_recruits),
            }
        )
    return {
        "schema": episode.schema_id,
        "execution_id": episode.execution_id,
        "status": episode.status,
        "core_templates": _string_list(episode.core_templates),
        "decisions": decisions[:12],
        "stop_reason": episode.stop_reason,
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
