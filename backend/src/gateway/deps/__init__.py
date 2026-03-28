"""Smaller dependency modules grouped by domain."""

from __future__ import annotations

from importlib import import_module

_EXPORT_MODULES = {
    "get_admin_dashboard_service": "src.gateway.deps.dashboard",
    "get_artifact_service": "src.gateway.deps.academic",
    "get_chat_thread_service": "src.gateway.deps.chat",
    "get_chat_turn_handler": "src.gateway.deps.application",
    "get_credit_service": "src.gateway.deps.dashboard",
    "get_dashboard_service": "src.gateway.deps.dashboard",
    "get_db": "src.gateway.deps.core",
    "get_feature_execution_handler": "src.gateway.deps.application",
    "get_literature_service": "src.gateway.deps.academic",
    "get_paper_service": "src.gateway.deps.academic",
    "get_papers_handler": "src.gateway.deps.application",
    "get_release_gate_service": "src.gateway.deps.dashboard",
    "get_task_service": "src.gateway.deps.tasks",
    "get_user_dashboard_service": "src.gateway.deps.dashboard",
    "get_workspace_activity_service": "src.gateway.deps.dashboard",
    "get_workspace_service": "src.gateway.deps.academic",
    "get_workspace_summary_service": "src.gateway.deps.dashboard",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
