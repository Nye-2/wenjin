"""Workflow runner for thesis generation.

This module provides the async runner that executes the thesis generation
workflow as a background task, updating task status in storage throughout.
"""

import logging
from typing import Any

from src.thesis.task_storage import get_storage
from src.thesis.workflow.graph import thesis_graph
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan
from src.thesis.config import thesis_settings

logger = logging.getLogger(__name__)


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
        # Step 3: Build section_plans and writing_order from framework_json
        framework = request.get("framework_json", {})
        section_plans = _build_section_plans(framework)
        writing_order = _build_writing_order(section_plans)

        # Update sections_total
        storage.update_task(task_id, {
            "sections_total": len(section_plans),
            "message": f"Planning {len(section_plans)} sections",
        })

        # Step 4: Build initial ThesisWorkflowState
        initial_state: ThesisWorkflowState = {
            "workspace_id": request.get("workspace_id", ""),
            "thread_id": task_id,
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

        # Step 5: Run thesis_graph.astream with streaming
        config = {
            "configurable": {
                "thread_id": task_id,
            }
        }

        logger.info(f"Starting workflow for task {task_id}")

        # Step 6: For each event, update task progress
        async for event in thesis_graph.astream(initial_state, config):
            logger.debug(f"Workflow event for task {task_id}: {event}")

            # Extract progress information from event
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    progress = node_output.get("progress", 0.0)
                    phase = node_output.get("current_phase", "")

                    # Update task progress
                    update_data = {"progress": progress}
                    if phase:
                        update_data["current_phase"] = phase
                        update_data["message"] = f"Processing: {phase}"

                    # Count completed sections
                    sections = node_output.get("sections", [])
                    if sections:
                        completed = sum(
                            1 for s in sections
                            if isinstance(s, dict) and s.get("status") == "completed"
                        )
                        update_data["sections_completed"] = completed

                    storage.update_task(task_id, update_data)

        # Step 7: After completion, get final state and update task with results
        final_state = thesis_graph.get_state(config)
        final_values = final_state.values

        latex_content = final_values.get("final_latex", "")
        pdf_path = final_values.get("pdf_path", "")
        bib_content = final_values.get("bib_content", "")
        final_progress = final_values.get("progress", 1.0)

        # Count final sections
        sections = final_values.get("sections", [])
        sections_completed = sum(
            1 for s in sections
            if isinstance(s, dict) and s.get("status") == "completed"
        )

        storage.update_task(task_id, {
            "status": "completed",
            "progress": 1.0,
            "current_phase": "completed",
            "latex_content": latex_content,
            "pdf_path": pdf_path,
            "bib_content": bib_content,
            "sections_completed": sections_completed,
            "message": "Thesis generation completed successfully",
        })

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
    "run_thesis_workflow",
]
