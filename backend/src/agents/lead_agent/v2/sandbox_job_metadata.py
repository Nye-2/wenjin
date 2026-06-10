"""Metadata helpers for lead-agent sandbox jobs."""

from __future__ import annotations

from typing import Any


def runtime_job_metadata(
    *,
    script_name: str | None = None,
    billing_reservation_id: str | None = None,
    command_audit: dict[str, Any] | None = None,
    task_scratch_path: str | None = None,
    task_contract: dict[str, Any] | None = None,
    execution_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {"source": "lead_agent_sandbox_runtime"}
    if script_name is not None:
        metadata["script_name"] = script_name
    if task_scratch_path:
        metadata["task_scratch_path"] = task_scratch_path
    if task_contract is not None:
        metadata["task_contract"] = dict(task_contract)
    if billing_reservation_id:
        metadata["credit_reservation_id"] = billing_reservation_id
    if command_audit is not None:
        metadata["command_audit"] = command_audit
    if execution_lifecycle is not None:
        metadata["execution_lifecycle"] = execution_lifecycle
    return metadata
