"""Application-layer request handlers."""

from src.application.handlers.academic_compat_handler import AcademicCompatHandler
from src.application.handlers.feature_execution_handler import (
    FeatureExecutionHandler,
    get_feature_execution_handler,
)
from src.application.handlers.papers_handler import PapersHandler
from src.application.handlers.thesis_api_handler import ThesisApiHandler

__all__ = [
    "AcademicCompatHandler",
    "FeatureExecutionHandler",
    "PapersHandler",
    "ThesisApiHandler",
    "get_feature_execution_handler",
]
