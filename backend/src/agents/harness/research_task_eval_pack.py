"""Curated deterministic eval-pack runner for Mission-native research evidence."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.agents.harness.research_task_eval import (
    EvalStatus,
    ResearchTaskEvidenceEval,
    evaluate_research_task_evidence,
)
from src.contracts.research_evidence import ResearchEvidenceBundle, ResearchSurface


class ResearchTaskEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    name: str
    workspace_type: str
    task_kind: str
    required_surfaces: tuple[ResearchSurface, ...]
    bundle: ResearchEvidenceBundle


class ResearchTaskEvalPackResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvalStatus
    case_count: int
    pass_count: int
    fail_count: int
    case_results: dict[str, ResearchTaskEvidenceEval]
    failed_cases: tuple[dict[str, object], ...]
    surface_failures: dict[str, tuple[str, ...]]


def evaluate_research_task_eval_pack(
    cases: list[ResearchTaskEvalCase] | tuple[ResearchTaskEvalCase, ...],
) -> ResearchTaskEvalPackResult:
    seen_case_ids: set[str] = set()
    case_results: dict[str, ResearchTaskEvidenceEval] = {}
    failed_cases: list[dict[str, object]] = []
    surface_failures: dict[str, list[str]] = {}
    pass_count = 0

    for case in cases:
        case_id = case.case_id.strip()
        if not case_id:
            raise ValueError("research eval case id is required")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate research eval case id: {case_id}")
        seen_case_ids.add(case_id)

        evaluation = evaluate_research_task_evidence(
            case.bundle,
            required_surfaces=case.required_surfaces,
        )
        case_results[case_id] = evaluation
        if evaluation.status == "pass":
            pass_count += 1
            continue

        failed_surfaces = tuple(surface for surface, status in evaluation.coverage.items() if status == "fail")
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

    fail_count = len(cases) - pass_count
    return ResearchTaskEvalPackResult(
        status="pass" if fail_count == 0 else "fail",
        case_count=len(cases),
        pass_count=pass_count,
        fail_count=fail_count,
        case_results=case_results,
        failed_cases=tuple(failed_cases),
        surface_failures={key: tuple(value) for key, value in surface_failures.items()},
    )
