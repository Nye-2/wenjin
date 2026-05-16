"""Application-handler dependency factories."""

from typing import Any

from fastapi import Depends

from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.gateway.deps.academic import (
    get_artifact_service,
    get_reference_index_service,
    get_reference_service,
    get_workspace_service,
)
from src.gateway.deps.threads import get_thread_service


async def get_thread_turn_handler(
    thread_service: Any = Depends(get_thread_service),
    workspace_service: Any = Depends(get_workspace_service),
    index_service: Any = Depends(get_reference_index_service),
    artifact_service: Any = Depends(get_artifact_service),
    reference_service: Any = Depends(get_reference_service),
) -> ThreadTurnHandler:
    """Construct a request-scoped thread turn handler."""
    return ThreadTurnHandler(
        thread_service=thread_service,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        reference_service=reference_service,
    )
