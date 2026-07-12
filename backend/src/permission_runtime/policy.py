"""Fail-closed permission policy for side-effecting Mission operations."""

from __future__ import annotations

from .contracts import PermissionContext, PermissionDisposition, PermissionEvaluation

_SAFE_OPERATIONS = frozenset({"read", "list", "inspect", "search_cached"})


def evaluate_permission(context: PermissionContext) -> PermissionEvaluation:
    if context.risk_level == "high":
        return PermissionEvaluation(
            disposition=PermissionDisposition.ASK,
            reason_code="high_risk_operation",
        )
    if context.secret_access or context.external_account:
        return PermissionEvaluation(
            disposition=PermissionDisposition.ASK,
            reason_code="external_authority_required",
        )
    if context.network_profile != "none":
        return PermissionEvaluation(
            disposition=PermissionDisposition.ASK,
            reason_code="network_access_required",
        )
    if context.operation in _SAFE_OPERATIONS and context.risk_level == "low":
        return PermissionEvaluation(
            disposition=PermissionDisposition.ALLOW,
            reason_code="low_risk_read",
        )
    if context.risk_level == "medium":
        return PermissionEvaluation(
            disposition=PermissionDisposition.ASK,
            reason_code="user_confirmation_required",
        )
    return PermissionEvaluation(
        disposition=PermissionDisposition.DENY,
        reason_code="unknown_operation",
    )


__all__ = ["evaluate_permission"]
