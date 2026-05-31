"""Sandbox policy validation."""

from __future__ import annotations

import re
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
_WORKSPACE_VENV_PYTHON = "/workspace/.wenjin/env/python/bin/python"
_SAFE_PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9_.!*+-]+)?$"
)


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
    operation: str = "run_python",
    language: str,
    command: str,
    policy_json: dict[str, Any],
    package_specs: list[str] | None = None,
) -> None:
    """Validate the DataService-level sandbox job contract."""

    if language != "python":
        raise DataServiceValidationError(
            "Sandbox jobs must use the Python language contract",
            detail={"language": language},
        )
    validate_sandbox_policy(policy_json)
    _validate_python_command(
        command,
        operation=operation,
        policy_json=policy_json,
        package_specs=package_specs,
    )


def validate_package_specs(package_specs: list[str]) -> list[str]:
    """Return normalized safe package specs for controlled installer commands."""

    normalized_specs: list[str] = []
    for raw in package_specs:
        value = " ".join(str(raw or "").strip().split())
        if (
            not value
            or "://" in value
            or value.startswith(("-", ".", "/"))
            or "@" in value
            or ";" in value
            or any(ch in value for ch in ("|", "&", "`", "$", "\\"))
        ):
            raise DataServiceValidationError(
                "Unsafe sandbox package spec",
                detail={"package": raw},
            )
        if not _SAFE_PACKAGE_RE.fullmatch(value):
            raise DataServiceValidationError(
                "Unsafe sandbox package spec",
                detail={"package": raw},
            )
        normalized_specs.append(value)
    return normalized_specs


def _validate_python_command(
    command: str,
    *,
    operation: str,
    policy_json: dict[str, Any],
    package_specs: list[str] | None,
) -> None:
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
    first = tokens[0] if tokens else ""
    first_lower = first.lower()
    allowed_python_entrypoints = {"python", "python3", _WORKSPACE_VENV_PYTHON}
    if first_lower not in allowed_python_entrypoints:
        raise DataServiceValidationError(
            "Sandbox command must start from a Python entrypoint",
            detail={"entrypoint": first, "allowed_entrypoints": sorted(allowed_python_entrypoints)},
        )
    if operation == "install_dependencies":
        _validate_install_command(tokens, policy_json=policy_json, package_specs=package_specs)
    elif operation not in {"run_python", "smoke_check"}:
        raise DataServiceValidationError(
            "Unsupported sandbox operation",
            detail={"operation": operation},
        )


def _validate_install_command(
    tokens: list[str],
    *,
    policy_json: dict[str, Any],
    package_specs: list[str] | None,
) -> None:
    if not bool(policy_json.get("allow_package_install", False)):
        raise DataServiceValidationError("Sandbox policy does not allow package installation")
    lowered = [token.lower() for token in tokens]
    if len(lowered) < 4 or lowered[1:3] != ["-m", "pip"] or lowered[3] not in {"install", "show"}:
        raise DataServiceValidationError(
            "Sandbox install command must use python -m pip install/show",
            detail={"command_shape": lowered[:4]},
        )
    raw_specs = list(package_specs or tokens[4:])
    if lowered[3] == "install":
        if not raw_specs:
            raise DataServiceValidationError("Sandbox install command requires at least one package")
        validate_package_specs(raw_specs)
    elif any(not str(item or "").strip() for item in raw_specs):
        raise DataServiceValidationError("Sandbox pip show command contains an empty package")
