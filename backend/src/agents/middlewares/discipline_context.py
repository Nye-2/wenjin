"""Discipline context middleware for injecting academic norms."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

# Discipline-specific norms database
DISCIPLINE_NORMS = {
    "computer_science": {
        "citation_style": "IEEE",
        "structure": [
            "Abstract",
            "Introduction",
            "Related Work",
            "Methodology",
            "Experiments",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "terminology": {
            "deep learning": "Deep Learning",
            "machine learning": "Machine Learning",
            "neural network": "Neural Network",
            "natural language processing": "Natural Language Processing (NLP)",
        },
        "writing_style": "technical and precise",
    },
    "biology": {
        "citation_style": "APA",
        "structure": [
            "Abstract",
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "terminology": {},
        "writing_style": "descriptive and detailed",
    },
    "physics": {
        "citation_style": "APS",
        "structure": [
            "Abstract",
            "Introduction",
            "Theory",
            "Methods",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "terminology": {},
        "writing_style": "mathematical and rigorous",
    },
    "psychology": {
        "citation_style": "APA",
        "structure": [
            "Abstract",
            "Introduction",
            "Method",
            "Results",
            "Discussion",
            "References",
        ],
        "terminology": {},
        "writing_style": "empirical and evidence-based",
    },
}

WORKSPACE_TYPE_CONFIGS = {
    "sci": {
        "paper_length": "6000-8000 words",
        "sections": 8,
        "figures": "3-5",
    },
    "thesis": {
        "paper_length": "30000-50000 words",
        "sections": 6,
        "figures": "10-20",
    },
    "proposal": {
        "paper_length": "2000-4000 words",
        "sections": 5,
        "figures": "2-3",
    },
    "grant": {
        "paper_length": "5000-10000 words",
        "sections": 6,
        "figures": "3-5",
    },
}


class DisciplineRegistry:
    """Registry for discipline-specific norms and configurations."""

    def get_norms(self, discipline: str, workspace_type: str | None = None) -> dict:
        """Get norms for a discipline and workspace type.

        Args:
            discipline: Academic discipline
            workspace_type: Type of workspace (sci, thesis, etc.)

        Returns:
            Dict with citation_style, structure, terminology, writing_style
        """
        # Get base discipline norms
        norms = DISCIPLINE_NORMS.get(discipline, DISCIPLINE_NORMS["computer_science"])

        # Add workspace type config
        if workspace_type:
            type_config = WORKSPACE_TYPE_CONFIGS.get(workspace_type, {})
            norms = {**norms, **type_config}

        return norms


class DisciplineContextMiddleware(Middleware):
    """Middleware that injects discipline-specific writing norms.

    This middleware:
    1. Gets discipline and workspace type from state
    2. Loads discipline-specific norms
    3. Injects into state for writing guidance
    """

    def __init__(self, discipline_registry: DisciplineRegistry | None = None):
        """Initialize with discipline registry.

        Args:
            discipline_registry: Registry for discipline norms
        """
        self.registry = discipline_registry or DisciplineRegistry()

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load and inject discipline norms."""
        discipline = state.discipline
        workspace_type = state.workspace_type

        if not discipline:
            return state.model_dump()

        # Load norms
        norms = self.registry.get_norms(discipline, workspace_type)
        return {
            **state.model_dump(),
            "_discipline_norms": norms,
        }
