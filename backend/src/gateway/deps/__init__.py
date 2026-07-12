"""Smaller dependency modules grouped by domain."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "get_admin_dashboard_service": "src.gateway.deps.dashboard",
    "get_artifact_service": "src.gateway.deps.academic",
    "get_thread_service": "src.gateway.deps.threads",
    "get_thread_turn_handler": "src.gateway.deps.application",
    "get_credit_service": "src.gateway.deps.dashboard",
    "get_dataservice_client": "src.gateway.deps.core",
    "get_reference_index_service": "src.gateway.deps.academic",
    "get_reference_service": "src.gateway.deps.academic",
    "get_release_gate_service": "src.gateway.deps.dashboard",
    "get_chat_turn_run_manager": "src.gateway.deps.runtime",
    "get_chat_turn_stream_bridge": "src.gateway.deps.runtime",
    "get_task_service": "src.gateway.deps.tasks",
    "get_template_service": "src.gateway.deps.academic",
    "get_upload_preprocessor": "src.gateway.deps.uploads",
    "get_user_dashboard_service": "src.gateway.deps.dashboard",
    "get_workspace_activity_service": "src.gateway.deps.dashboard",
    "get_workspace_service": "src.gateway.deps.academic",
    "get_workspace_summary_service": "src.gateway.deps.dashboard",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
