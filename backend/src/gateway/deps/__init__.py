"""Smaller dependency modules grouped by domain."""

from src.gateway.deps.academic import (
    get_artifact_service,
    get_literature_service,
    get_paper_service,
    get_workspace_service,
)
from src.gateway.deps.chat import get_chat_thread_service
from src.gateway.deps.core import get_db
from src.gateway.deps.dashboard import (
    get_admin_dashboard_service,
    get_credit_service,
    get_dashboard_service,
    get_release_gate_service,
    get_user_dashboard_service,
    get_workspace_activity_service,
    get_workspace_summary_service,
)
from src.gateway.deps.tasks import get_task_service

__all__ = [
    "get_admin_dashboard_service",
    "get_artifact_service",
    "get_chat_thread_service",
    "get_credit_service",
    "get_dashboard_service",
    "get_db",
    "get_literature_service",
    "get_paper_service",
    "get_release_gate_service",
    "get_task_service",
    "get_user_dashboard_service",
    "get_workspace_activity_service",
    "get_workspace_summary_service",
    "get_workspace_service",
]
