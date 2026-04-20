"""Application-handler dependency factories."""

from fastapi import Depends

from src.application.handlers.feature_execution_handler import FeatureExecutionHandler
from src.application.handlers.papers_handler import PapersHandler
from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.services import FeatureIngressService
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.academic import (
    get_artifact_service,
    get_index_service,
    get_literature_service,
    get_paper_service,
    get_workspace_service,
)
from src.gateway.deps.core import get_db
from src.gateway.deps.dashboard import get_credit_service
from src.gateway.deps.tasks import get_task_service
from src.gateway.deps.threads import get_thread_service
from src.gateway.deps.uploads import get_upload_preprocessor
from src.services.execution_session_service import ExecutionSessionService


async def get_feature_execution_handler(
    current_user=Depends(get_current_user),
    workspace_service=Depends(get_workspace_service),
    task_service=Depends(get_task_service),
    literature_service=Depends(get_literature_service),
    credit_service=Depends(get_credit_service),
) -> FeatureExecutionHandler:
    """Construct a request-scoped feature execution handler."""
    return FeatureExecutionHandler(
        actor_id=str(current_user.id),
        workspace_service=workspace_service,
        task_service=task_service,
        literature_service=literature_service,
        credit_service=credit_service,
    )


async def get_thread_turn_handler(
    thread_service=Depends(get_thread_service),
    workspace_service=Depends(get_workspace_service),
    index_service=Depends(get_index_service),
    artifact_service=Depends(get_artifact_service),
    paper_service=Depends(get_paper_service),
) -> ThreadTurnHandler:
    """Construct a request-scoped thread turn handler."""
    return ThreadTurnHandler(
        thread_service=thread_service,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        paper_service=paper_service,
    )


async def get_feature_launch_service(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    workspace_service=Depends(get_workspace_service),
    task_service=Depends(get_task_service),
    literature_service=Depends(get_literature_service),
    credit_service=Depends(get_credit_service),
) -> FeatureIngressService:
    """Construct a request-scoped feature launch service."""
    handler = FeatureExecutionHandler(
        actor_id=str(current_user.id),
        workspace_service=workspace_service,
        task_service=task_service,
        literature_service=literature_service,
        credit_service=credit_service,
    )
    return FeatureIngressService(
        actor_id=str(current_user.id),
        feature_execution_handler=handler,
        execution_session_service=ExecutionSessionService(db),
    )


async def get_papers_handler(
    paper_service=Depends(get_paper_service),
    workspace_service=Depends(get_workspace_service),
    task_service=Depends(get_task_service),
    upload_preprocessor=Depends(get_upload_preprocessor),
) -> PapersHandler:
    """Construct a request-scoped papers handler."""
    return PapersHandler(
        paper_service=paper_service,
        workspace_service=workspace_service,
        task_service=task_service,
        upload_preprocessor=upload_preprocessor,
    )
