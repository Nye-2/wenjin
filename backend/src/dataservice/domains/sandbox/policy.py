"""Sandbox policy validation."""

from __future__ import annotations

import shlex
from typing import Any

from src.dataservice.common.errors import DataServiceValidationError

FORBIDDEN_POLICY_FLAGS = {
    "allow_host_network",
    "allow_privileged",
    "allow_docker_socket",
    "allow_host_path_mounts",
    "allow_sibling_container_access",
    "allow_server_control",
}

FORBIDDEN_COMMAND_TOKENS = {
    "docker",
    "docker-compose",
    "kubectl",
    "systemctl",
    "service",
    "sudo",
    "mount",
    "umount",
    "ssh",
    "scp",
    "rsync",
}

FORBIDDEN_COMMAND_SUBSTRINGS = {
    "/var/run/docker.sock",
    "--privileged",
    "--network=host",
    "--network host",
    "/etc/passwd",
    "/etc/shadow",
}


def validate_sandbox_policy(policy: dict[str, Any]) -> None:
    """Reject policy snapshots that would allow host/container/server control."""

    enabled_forbidden_flags = [
        key for key in FORBIDDEN_POLICY_FLAGS if bool(policy.get(key))
    ]
    if enabled_forbidden_flags:
        raise DataServiceValidationError(
            "Sandbox policy enables forbidden host/container controls",
            detail={"enabled_flags": sorted(enabled_forbidden_flags)},
        )


def validate_python_job_contract(
    *,
    language: str,
    command: str,
    policy_json: dict[str, Any],
) -> None:
    """Validate the DataService-level sandbox job contract."""

    if language != "python":
        raise DataServiceValidationError(
            "Sandbox jobs must use the Python language contract",
            detail={"language": language},
        )
    validate_sandbox_policy(policy_json)
    _validate_python_command(command)


def _validate_python_command(command: str) -> None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized:
        raise DataServiceValidationError("Sandbox command cannot be empty")
    for forbidden in FORBIDDEN_COMMAND_SUBSTRINGS:
        if forbidden in normalized:
            raise DataServiceValidationError(
                "Sandbox command references forbidden host/container control",
                detail={"forbidden": forbidden},
            )
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise DataServiceValidationError(
            "Sandbox command is not shell-parseable",
            detail={"error": str(exc)},
        ) from exc
    lowered = [token.lower() for token in tokens]
    if any(token in FORBIDDEN_COMMAND_TOKENS for token in lowered):
        forbidden = sorted(set(lowered).intersection(FORBIDDEN_COMMAND_TOKENS))
        raise DataServiceValidationError(
            "Sandbox command uses forbidden host/container tooling",
            detail={"forbidden_tokens": forbidden},
        )
    first = lowered[0] if lowered else ""
    allowed_python_entrypoints = {"python", "python3"}
    if first not in allowed_python_entrypoints:
        raise DataServiceValidationError(
            "Sandbox command must start from a Python entrypoint",
            detail={"entrypoint": first, "allowed_entrypoints": sorted(allowed_python_entrypoints)},
        )
