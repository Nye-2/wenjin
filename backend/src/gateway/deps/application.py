"""Application-handler dependency factories."""

from fastapi import Depends

from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.services import FeatureIngressService, build_feature_ingress_service
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.academic import (
    get_artifact_service,
    get_reference_index_service,
    get_reference_service,
    get_workspace_service,
)
from src.gateway.deps.core import get_db
from src.gateway.deps.dashboard import get_credit_service
from src.gateway.deps.tasks import get_task_service
from src.gateway.deps.threads import get_thread_service


async def get_thread_turn_handler(
    thread_service=Depends(get_thread_service),
    workspace_service=Depends(get_workspace_service),
    index_service=Depends(get_reference_index_service),
    artifact_service=Depends(get_artifact_service),
    reference_service=Depends(get_reference_service),
) -> ThreadTurnHandler:
    """Construct a request-scoped thread turn handler."""
    return ThreadTurnHandler(
        thread_service=thread_service,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        reference_service=reference_service,
    )


async def get_feature_launch_service(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    workspace_service=Depends(get_workspace_service),
    task_service=Depends(get_task_service),
    reference_service=Depends(get_reference_service),
    credit_service=Depends(get_credit_service),
) -> FeatureIngressService:
    """Construct a request-scoped feature launch service."""
    return build_feature_ingress_service(
        actor_id=str(current_user.id),
        db=db,
        workspace_service=workspace_service,
        task_service=task_service,
        reference_service=reference_service,
        credit_service=credit_service,
    )
