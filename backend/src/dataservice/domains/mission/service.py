"""Canonical composed transaction service for the durable Mission aggregate."""

from src.dataservice.domains.mission._store_core import (
    MissionProjectionStaleError,
    _MissionStoreCore,
)
from src.dataservice.domains.mission._store_execution import MissionExecutionOperations
from src.dataservice.domains.mission._store_lifecycle import MissionLifecycleOperations
from src.dataservice.domains.mission._store_queries import MissionQueryOperations
from src.dataservice.domains.mission._store_review import MissionReviewOperations


class MissionStore(
    MissionLifecycleOperations,
    MissionExecutionOperations,
    MissionReviewOperations,
    MissionQueryOperations,
    _MissionStoreCore,
):
    """Single DataService transaction boundary for the durable Mission aggregate."""


__all__ = [
    "MissionProjectionStaleError",
    "MissionStore",
]
