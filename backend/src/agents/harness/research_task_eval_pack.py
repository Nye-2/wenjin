"""Curated acceptance-pack runner for deterministic research-task evals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.agents.contracts.task_report import TaskReport
from src.agents.harness.research_eval_surfaces import ResearchSurface

from .research_task_eval import (
    EvalStatus,
    ResearchTaskEvidenceEval,
    evaluate_research_task_evidence,
)


@dataclass(frozen=True, slots=True)
class ResearchTaskEvalCase:
    """One deterministic acceptance case for a research-task output."""

    case_id: str
    name: str
    workspace_type: str
    task_kind: str
    required_surfaces: tuple[ResearchSurface, ...]
    report: TaskReport
    node_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResearchTaskEvalPackResult:
    """Aggregated result for a small curated research-task eval pack."""

    status: EvalStatus
    case_count: int
    pass_count: int
    fail_count: int
    case_results: dict[str, ResearchTaskEvidenceEval]
    failed_cases: list[dict[str, Any]]
    surface_failures: dict[str, list[str]]


def evaluate_research_task_eval_pack(
    cases: list[ResearchTaskEvalCase] | tuple[ResearchTaskEvalCase, ...],
) -> ResearchTaskEvalPackResult:
    """Evaluate a curated set of deterministic research-task fixtures."""

    seen_case_ids: set[str] = set()
    case_results: dict[str, ResearchTaskEvidenceEval] = {}
    failed_cases: list[dict[str, Any]] = []
    surface_failures: dict[str, list[str]] = {}
    pass_count = 0

    for case in cases:
        case_id = str(case.case_id or "").strip()
        if not case_id:
            raise ValueError("research eval case id is required")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate research eval case id: {case_id}")
        seen_case_ids.add(case_id)

        evaluation = evaluate_research_task_evidence(
            case.report,
            node_events=case.node_events,
            required_surfaces=case.required_surfaces,
        )
        case_results[case_id] = evaluation
        if evaluation.status == "pass":
            pass_count += 1
            continue

        failed_surfaces = [
            surface
            for surface, status in evaluation.coverage.items()
            if status == "fail"
        ]
        for surface in failed_surfaces:
            surface_failures.setdefault(surface, []).append(case_id)
        failed_cases.append(
            {
                "case_id": case_id,
                "name": case.name,
                "workspace_type": case.workspace_type,
                "task_kind": case.task_kind,
                "failed_surfaces": failed_surfaces,
            }
        )

    case_count = len(cases)
    fail_count = case_count - pass_count
    return ResearchTaskEvalPackResult(
        status="pass" if fail_count == 0 else "fail",
        case_count=case_count,
        pass_count=pass_count,
        fail_count=fail_count,
        case_results=case_results,
        failed_cases=failed_cases,
        surface_failures=surface_failures,
    )
