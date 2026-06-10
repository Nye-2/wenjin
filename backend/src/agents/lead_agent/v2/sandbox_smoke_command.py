"""Smoke-check command contract for lead-agent sandbox runtime."""

from __future__ import annotations

from src.agents.harness.command_audit import (
    CommandAuditPolicy,
    CommandAuditResult,
    HarnessCommand,
    audit_command,
    require_command_policy_allowed,
)

SMOKE_COMMAND = (
    "PYTHON_BIN=$(command -v python || command -v python3) && "
    "\"$PYTHON_BIN\" -c \"import json, platform, statistics; "
    "data=[2,4,6,8]; "
    "print(json.dumps({'ok': True, 'mean': statistics.mean(data), "
    "'python': platform.python_version(), 'engine': 'lead_agent_docker_sandbox'}, "
    "ensure_ascii=False, sort_keys=True))\""
)


def smoke_command_audit() -> CommandAuditResult:
    result = audit_command(
        HarnessCommand(
            shell_command=SMOKE_COMMAND,
            operation="smoke_check",
            billable=True,
        ),
        CommandAuditPolicy(allow_shell=True),
    )
    require_command_policy_allowed(result)
    return result
