# src/thesis/workflow/nodes/assembler.py
"""LaTeX assembler node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.latex_template import get_template
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


def generate_bibtex(references: list[dict[str, Any]]) -> str:
    """Generate BibTeX content from references.

    Args:
        references: List of reference dictionaries with 'bibtex' field

    Returns:
        Combined BibTeX content
    """
    entries = []
    for ref in references:
        bibtex = ref.get("bibtex", "")
        if bibtex:
            entries.append(bibtex)
    return "\n\n".join(entries)


def assemble_latex_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Assemble complete LaTeX document from sections.

    This node:
    1. Collects all completed section content
    2. Generates LaTeX preamble from template
    3. Assembles full document
    4. Generates BibTeX content

    Args:
        state: Current workflow state

    Returns:
        State updates with final LaTeX and BibTeX content
    """
    log_node_start("assembler", state)

    def get_section_attr(s, attr):
        """Handle both Pydantic models and dict objects."""
        if isinstance(s, dict):
            return s.get(attr)
        return getattr(s, attr, None)

    # Sort sections by index
    sections = sorted(
        state.get("sections", []),
        key=lambda s: get_section_attr(s, "index") or 0
    )

    # Combine section content
    content_parts = []
    for section in sections:
        content = get_section_attr(section, "content")
        if content:
            content_parts.append(content)

    main_content = "\n\n".join(content_parts)

    # Generate abstract (Chinese + English)
    abstract = state.get("abstract_content", "")
    abstract_latex = f"\\begin{{abstract}}\n{abstract}\n\\end{{abstract}}\n"

    # Fill template
    template = get_template("zh")  # Default to Chinese
    final_latex = template.format(
        title=state.get("paper_title", "未命名论文"),
        author="",  # To be filled by user
        abstract=abstract_latex,
        content=main_content,
        acknowledgements="",  # To be filled by user
    )

    # Generate BibTeX
    references = state.get("references", [])
    bib_content = generate_bibtex(references)

    log_node_end("assembler", state, {"progress": 0.95})

    return {
        "final_latex": final_latex,
        "bib_content": bib_content,
        "current_phase": "assembly",
        "progress": 0.95,
    }
