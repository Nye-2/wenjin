"""Budget-reduction policy for harness context bundles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def fit_context_bundle_to_budget(
    bundle: dict[str, Any],
    max_chars: int,
    *,
    render: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Return a copy of the bundle reduced to the prompt budget when possible."""

    if len(render(bundle)) <= max_chars:
        return bundle
    compact = dict(bundle)
    compact["budget"] = {"max_chars": max_chars, "truncated": True}
    compact["sandbox"] = dict(bundle.get("sandbox") or {})
    compact["recent_execution_evidence"] = list(bundle.get("recent_execution_evidence") or [])
    while compact["recent_execution_evidence"] and len(render(compact)) > max_chars:
        compact["recent_execution_evidence"].pop()
    _drop_sandbox_verbose_context(compact, max_chars=max_chars, render=render)
    for key, empty in _budget_drop_candidates(compact, protected_only=False):
        if len(render(compact)) <= max_chars:
            break
        compact[key] = empty
    _drop_task_generic_budget_context(compact, max_chars=max_chars, render=render)
    _drop_structural_budget_context(compact, max_chars=max_chars, render=render)
    for key, empty in _budget_drop_candidates(compact, protected_only=True):
        if len(render(compact)) <= max_chars:
            break
        compact[key] = empty
    _drop_structural_budget_context(compact, max_chars=max_chars, render=render)
    if len(render(compact)) > max_chars:
        compact["task"] = {}
    return compact


def _drop_task_generic_budget_context(
    compact: dict[str, Any],
    *,
    max_chars: int,
    render: Callable[[dict[str, Any]], str],
) -> None:
    if len(render(compact)) <= max_chars:
        return
    task = compact.get("task")
    if not isinstance(task, dict):
        return
    inputs = task.get("inputs")
    if not isinstance(inputs, dict):
        return
    upstream_context = inputs.get("upstream_context")
    if not isinstance(upstream_context, dict):
        return

    compact_task = dict(task)
    compact_inputs = dict(inputs)
    compact_upstream = dict(upstream_context)
    for key in (
        "artifact_candidates",
        "upstream_artifact_candidates",
        "sandbox_outputs",
        "upstream_sandbox_outputs",
    ):
        compact_upstream.pop(key, None)
    if compact_upstream:
        compact_inputs["upstream_context"] = compact_upstream
    else:
        compact_inputs.pop("upstream_context", None)
    compact_task["inputs"] = compact_inputs
    compact["task"] = compact_task


def _drop_structural_budget_context(
    compact: dict[str, Any],
    *,
    max_chars: int,
    render: Callable[[dict[str, Any]], str],
) -> None:
    if len(render(compact)) > max_chars:
        compact["workspace_file_summary"] = {
            "visible_roots": [],
            "recent_outputs": [],
            "recent_scripts": [],
            "truncated": True,
        }
    if len(render(compact)) > max_chars:
        compact["sandbox"].pop("rules", None)
    if len(render(compact)) > max_chars:
        compact["sandbox"].pop("search_ignored_names", None)
    if len(render(compact)) > max_chars:
        compact.pop("workspace_file_summary", None)
    if len(render(compact)) > max_chars:
        compact["sandbox"] = {"root": str(compact.get("sandbox", {}).get("root") or "/workspace")}


def _budget_drop_candidates(
    bundle: dict[str, Any],
    *,
    protected_only: bool,
) -> list[tuple[str, Any]]:
    candidates = [
        ("upstream_artifact_candidates", []),
        ("harness_replan_signals", []),
        ("recent_file_change_summary", {}),
        ("statistical_robustness_summary", {}),
        ("experiment_interpretation_summary", {}),
        ("reproducibility_summary", {}),
        ("member_execution_transcript", {}),
        ("output_ref_recovery", {}),
        ("sandbox_execution_summary", {}),
        ("scratch_refs", []),
    ]
    protected = _required_research_context_keys(bundle)
    return [
        (key, empty)
        for key, empty in candidates
        if (key in protected) is protected_only
    ]


def _required_research_context_keys(bundle: dict[str, Any]) -> set[str]:
    requirements = _research_evidence_requirements(bundle)
    surfaces = set(_safe_string_list(requirements.get("required_surfaces")))
    protected: set[str] = set()
    if "workflow_trace" in surfaces:
        protected.update({"member_execution_transcript", "scratch_refs"})
    if "output_ref_reuse" in surfaces:
        protected.update(
            {
                "sandbox_execution_summary",
                "output_ref_recovery",
                "member_execution_transcript",
            }
        )
    if "experiment_interpretation" in surfaces:
        protected.update({"experiment_interpretation_summary", "reproducibility_summary"})
    if "statistical_robustness" in surfaces:
        protected.update({"statistical_robustness_summary", "reproducibility_summary"})
    return protected


def _research_evidence_requirements(bundle: dict[str, Any]) -> dict[str, Any]:
    task = bundle.get("task")
    task = task if isinstance(task, dict) else {}
    inputs = task.get("inputs")
    inputs = inputs if isinstance(inputs, dict) else {}
    requirements = inputs.get("research_evidence_requirements")
    if isinstance(requirements, dict):
        return requirements
    requirements = task.get("research_evidence_requirements")
    return requirements if isinstance(requirements, dict) else {}


def _drop_sandbox_verbose_context(
    compact: dict[str, Any],
    *,
    max_chars: int,
    render: Callable[[dict[str, Any]], str],
) -> None:
    sandbox = compact.get("sandbox")
    if not isinstance(sandbox, dict):
        return
    task_contract = sandbox.get("task_contract")
    if isinstance(task_contract, dict) and len(render(compact)) > max_chars:
        task_contract = dict(task_contract)
        task_contract.pop("rules", None)
        sandbox["task_contract"] = task_contract
    for key in (
        "rules",
        "search_ignored_names",
        "guidance_paths",
        "protected_paths",
        "internal_paths",
    ):
        if len(render(compact)) <= max_chars:
            return
        sandbox.pop(key, None)


def _safe_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set | frozenset):
        raw = list(value)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result
