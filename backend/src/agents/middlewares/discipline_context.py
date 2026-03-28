"""Discipline context middleware for injecting academic norms."""

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

DISCIPLINE_NORMS_PATH = Path(__file__).parent / "discipline_norms.yaml"

_DEFAULT_DISCIPLINE = "computer_science"


def _load_norms_config() -> dict[str, Any]:
    """Load discipline norms from the YAML config file.

    Returns:
        Dict with 'disciplines' and 'workspace_types' keys.
    """
    try:
        text = DISCIPLINE_NORMS_PATH.read_text(encoding="utf-8")
        config = yaml.safe_load(text)
        if not isinstance(config, dict):
            logger.warning("discipline_norms.yaml did not parse as a dict, using empty config")
            return {"disciplines": {}, "workspace_types": {}}
        return config
    except FileNotFoundError:
        logger.warning("discipline_norms.yaml not found at %s, using empty config", DISCIPLINE_NORMS_PATH)
        return {"disciplines": {}, "workspace_types": {}}
    except yaml.YAMLError as exc:
        logger.error("Failed to parse discipline_norms.yaml: %s", exc)
        return {"disciplines": {}, "workspace_types": {}}


class DisciplineRegistry:
    """Registry for discipline-specific norms and configurations."""

    def __init__(self) -> None:
        config = _load_norms_config()
        self._disciplines: dict[str, Any] = config.get("disciplines", {})
        self._workspace_types: dict[str, Any] = config.get("workspace_types", {})

    def get_norms(self, discipline: str, workspace_type: str | None = None) -> dict:
        """Get norms for a discipline and workspace type.

        Args:
            discipline: Academic discipline
            workspace_type: Type of workspace (sci, thesis, etc.)

        Returns:
            Dict with citation_style, structure, terminology, writing_style
        """
        # Get base discipline norms
        default = self._disciplines.get(_DEFAULT_DISCIPLINE, {})
        norms = self._disciplines.get(discipline, default)

        # Add workspace type config
        if workspace_type:
            type_config = self._workspace_types.get(workspace_type, {})
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
        discipline = state.get("discipline")
        workspace_type = state.get("workspace_type")

        if not discipline:
            return dict(state)

        # Load norms
        norms = self.registry.get_norms(discipline, workspace_type)
        return {
            **state,
            "discipline_norms": norms,
        }
