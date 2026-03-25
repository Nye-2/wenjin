"""Task handlers for unified task dispatch."""

from src.task.handlers.paper_extraction_handler import execute_paper_extraction
from src.task.handlers.workspace_feature_handler import (
    execute_workspace_feature,
)

__all__ = [
    "execute_paper_extraction",
    "execute_workspace_feature",
]
