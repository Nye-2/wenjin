"""Compatibility re-export for shared gateway dependency factories."""

from src.gateway.deps import (
    get_admin_dashboard_service,
    get_artifact_service,
    get_chat_thread_service,
    get_credit_service,
    get_dashboard_service,
    get_db,
    get_literature_service,
    get_paper_service,
    get_release_gate_service,
    get_task_service,
    get_user_dashboard_service,
    get_workspace_service,
)

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
    "get_workspace_service",
]
