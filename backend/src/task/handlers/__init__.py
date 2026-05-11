"""Task handlers for unified task dispatch."""

from src.task.handlers.document_preprocess_handler import execute_document_preprocess
from src.task.handlers.reference_preprocess_handler import execute_reference_preprocess

__all__ = [
    "execute_document_preprocess",
    "execute_reference_preprocess",
]
