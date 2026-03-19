"""Workflow runner for thesis generation.

This module provides the async runner that executes the thesis generation
workflow as a background task, updating task status in storage throughout.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.thesis.config import thesis_settings
from src.thesis.task_storage import get_storage
from src.thesis.workflow.graph import thesis_graph
from src.thesis.workflow.state import SectionPlan, ThesisWorkflowState

logger = logging.getLogger(__name__)
StatusUpdateCallback = Callable[[dict[str, Any]], Awaitable[None]]


def _build_section_plans(framework: dict[str, Any]) -> list[SectionPlan]:
    """Convert framework_json to SectionPlan list.

    Args:
        framework: The framework JSON dict containing section definitions

    Returns:
        List of SectionPlan objects
    """
    sections = framework.get("sections", [])
    plans = []

    for section in sections:
        plan = SectionPlan(
            index=section.get("index", len(plans) + 1),
            title=section.get("title", f"Section {len(plans) + 1}"),
            purpose=section.get("purpose", ""),
            key_points=section.get("key_points", []),
            target_words=section.get("target_words", thesis_settings.default_target_words),
            dependencies=section.get("dependencies", []),
            literature_needs=section.get("literature_needs", []),
        )
        plans.append(plan)

    return plans


def _build_writing_order(plans: list[SectionPlan]) -> list[int]:
    """Determine writing order based on section plans and dependencies.

    Uses a simple topological sort to respect dependencies.

    Args:
        plans: List of SectionPlan objects

    Returns:
        List of section indices in writing order
    """
    if not plans:
        return []

    # Build dependency graph
    plan_by_index = {p.index: p for p in plans}
    all_indices = set(plan_by_index.keys())

    # Simple topological sort using Kahn's algorithm
    # Count incoming edges for each node
    in_degree = {idx: 0 for idx in all_indices}
    for plan in plans:
        for dep in plan.dependencies:
            if dep in in_degree:
                in_degree[plan.index] += 1

    # Start with nodes that have no dependencies
    queue = [idx for idx, degree in in_degree.items() if degree == 0]
    queue.sort()  # Ensure deterministic order

    result = []
    while queue:
        # Take the smallest index to ensure deterministic order
        queue.sort()
        current = queue.pop(0)
        result.append(current)

        # Reduce in-degree for dependent sections
        for plan in plans:
            if current in plan.dependencies:
                in_degree[plan.index] -= 1
                if in_degree[plan.index] == 0:
                    queue.append(plan.index)

    # If we couldn't process all nodes (cycle), fall back to simple order
    if len(result) != len(all_indices):
        logger.warning("Dependency cycle detected, falling back to simple order")
        return sorted(all_indices)

    return result


def _count_completed_sections(sections: list[Any]) -> int:
    """Count completed sections across dict and model payloads."""
    completed = 0
    for section in sections:
        status = getattr(section, "status", None)
        if status is None and isinstance(section, dict):
            status = section.get("status")
        if status == "completed":
            completed += 1
    return completed


def _build_initial_state(
    request: dict[str, Any],
    section_plans: list[SectionPlan],
    writing_order: list[int],
) -> ThesisWorkflowState:
    """Build the initial thesis workflow state."""
    framework = request.get("framework_json", {})
    return {
        "workspace_id": request.get("workspace_id", ""),
        "thread_id": request.get("thread_id", ""),
        "paper_title": request.get("paper_title", "Untitled"),
        "discipline": request.get("discipline", "计算机科学"),
        "abstract_content": request.get("abstract_content", ""),
        "framework_json": framework,
        "section_plans": [p.model_dump() for p in section_plans],  # type: ignore
        "writing_order": writing_order,
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "init",
        "progress": 0.0,
        "errors": [],
    }


def _extract_update(
    node_output: dict[str, Any],
    *,
    sections_total: int,
) -> dict[str, Any]:
    """Extract a normalized status update from a workflow node output."""
    update: dict[str, Any] = {
        "progress": float(node_output.get("progress", 0.0)),
        "sections_total": sections_total,
    }
    phase = node_output.get("current_phase")
    if phase:
        update["current_phase"] = phase
        update["message"] = f"Processing: {phase}"

    sections = node_output.get("sections")
    if sections:
        update["sections_completed"] = _count_completed_sections(sections)

    if "final_latex" in node_output:
        update["latex_content"] = node_output.get("final_latex", "")
    if "bib_content" in node_output:
        update["bib_content"] = node_output.get("bib_content", "")
    if "pdf_path" in node_output:
        update["pdf_path"] = node_output.get("pdf_path", "")

    return update


def _build_final_result(
    final_values: dict[str, Any],
    *,
    sections_total: int,
) -> dict[str, Any]:
    """Normalize the final workflow state into a task result payload."""
    sections = final_values.get("sections", [])
    return {
        "current_phase": final_values.get("current_phase", "completed"),
        "progress": float(final_values.get("progress", 1.0)),
        "latex_content": final_values.get("final_latex", ""),
        "pdf_path": final_values.get("pdf_path", ""),
        "bib_content": final_values.get("bib_content", ""),
        "sections_completed": _count_completed_sections(sections),
        "sections_total": sections_total,
    }


async def run_thesis_workflow_request(
    request: dict[str, Any],
    *,
    on_update: StatusUpdateCallback | None = None,
) -> dict[str, Any]:
    """Run thesis generation and emit normalized progress updates."""
    framework = request.get("framework_json", {})
    section_plans = _build_section_plans(framework)
    writing_order = _build_writing_order(section_plans)
    sections_total = len(section_plans)

    if on_update:
        await on_update(
            {
                "status": "running",
                "current_phase": "init",
                "progress": 0.0,
                "sections_completed": 0,
                "sections_total": sections_total,
                "message": "Starting thesis generation workflow",
            }
        )

    initial_state = _build_initial_state(request, section_plans, writing_order)
    config = {
        "configurable": {
            "thread_id": request.get("thread_id") or request.get("task_id") or request.get("workspace_id", ""),
        }
    }

    logger.info("Starting thesis workflow for workspace %s", request.get("workspace_id", ""))

    async for event in thesis_graph.astream(initial_state, config):
        logger.debug("Thesis workflow event: %s", event)
        for node_output in event.values():
            if isinstance(node_output, dict) and on_update:
                await on_update(_extract_update(node_output, sections_total=sections_total))

    final_state = thesis_graph.get_state(config)
    final_values = final_state.values
    result = _build_final_result(final_values, sections_total=sections_total)

    if on_update:
        await on_update(
            {
                "status": "completed",
                "message": "Thesis generation completed successfully",
                **result,
            }
        )

    return result


async def run_thesis_workflow(task_id: str, request: dict[str, Any]) -> None:
    """Run the thesis generation workflow as a background task.

    This is the main entry point for executing the thesis generation workflow.
    It updates task status throughout execution and handles errors gracefully.

    Args:
        task_id: The unique identifier for the task
        request: The request dict containing:
            - workspace_id: Workspace ID
            - paper_title: Thesis title
            - discipline: Academic discipline
            - abstract_content: Abstract text
            - framework_json: Framework with section definitions
    """
    storage = get_storage()

    # Step 1: Get task from storage, return if not found
    task = storage.get_task(task_id)
    if not task:
        logger.warning(f"Task {task_id} not found, skipping workflow")
        return

    # Step 2: Update task status to "running", phase to "init"
    storage.update_task(task_id, {
        "status": "running",
        "current_phase": "init",
        "message": "Starting thesis generation workflow",
    })

    try:
        async def on_update(update: dict[str, Any]) -> None:
            storage_update = {}
            for key in (
                "status",
                "progress",
                "current_phase",
                "message",
                "latex_content",
                "pdf_path",
                "bib_content",
                "sections_completed",
                "sections_total",
                "error",
            ):
                if key in update:
                    storage_update[key] = update[key]
            if storage_update:
                storage.update_task(task_id, storage_update)

        await run_thesis_workflow_request(
            {
                **request,
                "task_id": task_id,
                "thread_id": task_id,
            },
            on_update=on_update,
        )

        logger.info(f"Workflow completed for task {task_id}")

    except Exception as e:
        # Step 8: On exception, update task status to "failed" with error message
        error_message = str(e)
        logger.error(f"Workflow failed for task {task_id}: {error_message}", exc_info=True)

        storage.update_task(task_id, {
            "status": "failed",
            "error": error_message,
            "message": f"Workflow failed: {error_message}",
        })


__all__ = [
    "_build_section_plans",
    "_build_writing_order",
    "run_thesis_workflow_request",
    "run_thesis_workflow",
]
