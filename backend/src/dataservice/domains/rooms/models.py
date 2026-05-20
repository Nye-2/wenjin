"""Canonical room table aliases.

The current decision, memory, and task tables already match the target
aggregate shape. DataService owns their repositories and service logic while
the physical SQLAlchemy models stay in ``src.database.models`` until the final
legacy deletion/archive gate.
"""

from __future__ import annotations

from src.database.models.decision import Decision as DecisionRecord
from src.database.models.memory_fact import MemoryFact as MemoryFactRecord
from src.database.models.workspace_task import WorkspaceTask as WorkspaceTaskRecord

__all__ = ["DecisionRecord", "MemoryFactRecord", "WorkspaceTaskRecord"]
