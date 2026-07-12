"""Structured research output contracts used by quality evaluation."""
from .task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    ResultError,
    ResultOutput,
    ResultOutputBase,
    TaskData,
    TaskOutput,
    TaskReport,
)

__all__ = [
    "TaskReport",
    "ResultOutput",
    "ResultOutputBase",
    "LibraryItemOutput",
    "LibraryItemData",
    "DocumentOutput",
    "DocumentData",
    "MemoryFactOutput",
    "MemoryFactData",
    "DecisionOutput",
    "DecisionData",
    "TaskOutput",
    "TaskData",
    "ResultError",
]
