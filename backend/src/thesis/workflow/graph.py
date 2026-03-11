# src/thesis/workflow/graph.py
"""LangGraph workflow definition for thesis generation.

This module defines the StateGraph that orchestrates all 6 nodes:
    literature_search -> section_writer -> figure_planner -> figure_generator -> assembler -> compiler -> END
                              |
                              +-- (loop until all sections done) --+
"""

import logging
from typing import Any, Literal

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes import (
    literature_search_node,
    section_writer_node,
    assemble_latex_node,
    figure_planner_node,
    figure_generator_node,
    compile_latex_node,
)
from src.thesis.workflow.nodes.base import get_attr

logger = logging.getLogger(__name__)

# Routing constants
ROUTE_CONTINUE = "continue_writing"
ROUTE_DONE = "done_writing"


def should_continue_writing(state: ThesisWorkflowState) -> Literal["continue_writing", "done_writing"]:
    """Determine if section writing should continue or move to figure planning.

    This function checks if there are any sections that still need to be written
    by comparing the writing_order with completed sections.

    Args:
        state: Current workflow state

    Returns:
        ROUTE_CONTINUE if more sections need writing, ROUTE_DONE if all completed
    """
    writing_order = state.get("writing_order", [])
    sections = state.get("sections", [])

    # Get completed section indices
    completed_indices = {
        get_attr(s, "index")
        for s in sections
        if get_attr(s, "status", "pending") == "completed"
    }

    # Check if any section in writing_order is not completed
    for idx in writing_order:
        if idx not in completed_indices:
            logger.debug(f"Section {idx} not completed, continuing writing")
            return ROUTE_CONTINUE

    logger.info("All sections completed, proceeding to figure planning")
    return ROUTE_DONE


def build_thesis_graph() -> StateGraph:
    """Build and compile the thesis generation workflow graph.

    The graph structure is:
        literature_search -> section_writer -> figure_planner -> figure_generator -> assembler -> compiler -> END
                                |
                                +-- (loop until all sections done) --+

    The section_writer node loops back to itself until all sections are completed.

    Returns:
        Compiled StateGraph with MemorySaver checkpointer
    """
    # Create the graph builder with the state schema
    builder = StateGraph(ThesisWorkflowState)

    # Add all 6 nodes
    builder.add_node("literature_search", literature_search_node)
    builder.add_node("section_writer", section_writer_node)
    builder.add_node("figure_planner", figure_planner_node)
    builder.add_node("figure_generator", figure_generator_node)
    builder.add_node("assembler", assemble_latex_node)
    builder.add_node("compiler", compile_latex_node)

    # Set entry point
    builder.set_entry_point("literature_search")

    # Add edges
    # literature_search -> section_writer
    builder.add_edge("literature_search", "section_writer")

    # section_writer conditional edges (loop until done)
    builder.add_conditional_edges(
        "section_writer",
        should_continue_writing,
        {
            ROUTE_CONTINUE: "section_writer",  # Loop back to write next section
            ROUTE_DONE: "figure_planner",  # All done, proceed to figures
        },
    )

    # figure_planner -> figure_generator
    builder.add_edge("figure_planner", "figure_generator")

    # figure_generator -> assembler
    builder.add_edge("figure_generator", "assembler")

    # assembler -> compiler
    builder.add_edge("assembler", "compiler")

    # compiler -> END
    builder.add_edge("compiler", END)

    # Compile with MemorySaver for checkpointing
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("Thesis workflow graph built and compiled successfully")
    return graph


# Global instance for convenience
thesis_graph = build_thesis_graph()
