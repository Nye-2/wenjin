"""Stable contracts for the Wenjin-native agent harness."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from src.sandbox.workspace_layout import WORKSPACE_PROTECTED_PATHS

HarnessRiskLevel = Literal["read", "write", "execute", "network", "review"]
HarnessVisibility = Literal["user_visible", "team_visible", "debug_only"]
HarnessToolStatus = Literal["ok", "warning", "error"]
HarnessPermissionDecision = Literal["allow", "ask", "deny"]
HarnessStopReason = Literal[
    "completed",
    "schema_invalid",
    "tool_forbidden",
    "tool_unknown",
    "tool_loop_hard_stop",
    "sandbox_queue_timeout",
    "sandbox_job_failed",
    "model_safety_suppressed",
    "aborted",
    "max_iterations",
]


@dataclass(frozen=True, slots=True)
class HarnessRunContext:
    """Product execution context passed into the harness boundary."""

    workspace_id: str
    user_id: str
    execution_id: str
    node_id: str
    invocation_id: str
    workspace_type: str
    capability_id: str
    capability_policy: dict[str, Any] = field(default_factory=dict)
    agent_template: dict[str, Any] = field(default_factory=dict)
    skill: dict[str, Any] = field(default_factory=dict)
    context_bundle: dict[str, Any] = field(default_factory=dict)
    requested_tools: tuple[str, ...] = ()
    abort_check: Callable[[str], Awaitable[bool]] | None = None
    publish_event: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class HarnessPolicy:
    """Effective permissions for one harness invocation."""

    allowed_tools: tuple[str, ...] = ()
    denied_tools: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    filesystem_roots: tuple[str, ...] = ("/workspace",)
    protected_paths: tuple[str, ...] = WORKSPACE_PROTECTED_PATHS
    network_profile: str = "none"
    allow_package_install: bool = False
    max_tool_calls: int = 30
    max_iterations: int = 8
    max_sandbox_seconds: int = 120
    output_budget: dict[str, Any] = field(default_factory=dict)
    visibility_defaults: dict[str, HarnessVisibility] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarnessToolSpec:
    """Serializable tool declaration used by policy and adapters."""

    name: str
    namespace: str
    description: str
    input_schema: dict[str, Any]
    risk_level: HarnessRiskLevel
    required_permissions: list[str] = field(default_factory=list)
    output_policy: dict[str, Any] = field(default_factory=dict)
    user_visibility: HarnessVisibility = "debug_only"
    deferred: bool = False


@dataclass(frozen=True, slots=True)
class HarnessToolResult:
    """Bounded result returned from a harness tool implementation."""

    preview_text: str
    structured_payload: dict[str, Any] = field(default_factory=dict)
    output_refs: tuple[str, ...] = ()
    truncated: bool = False
    externalized: bool = False
    error: str | None = None
    file_change: dict[str, Any] | None = None
    file_changes: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class AcademicACIObservation:
    """Bounded structured observation returned from an Academic ACI tool."""

    tool: str
    status: HarnessToolStatus
    summary: str
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    structured_payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": "wenjin.academic_aci.observation.v1",
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "output_refs": list(self.output_refs),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
            "structured_payload": dict(self.structured_payload),
        }


@dataclass(frozen=True, slots=True)
class AcademicACIPermissionCheck:
    """Permission decision for an Academic ACI tool call."""

    tool: str
    decision: HarnessPermissionDecision
    reason: str
    required_permissions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": "wenjin.academic_aci.permission_check.v1",
            "tool": self.tool,
            "decision": self.decision,
            "reason": self.reason,
            "required_permissions": list(self.required_permissions),
        }
