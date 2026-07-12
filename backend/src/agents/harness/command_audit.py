"""Mandatory audit for commands compiled from typed sandbox operations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from src.sandbox.contracts import (
    CommandAuditEvidence,
    CompiledSandboxCommand,
    SandboxNetworkProfile,
    SandboxOperationKind,
    SandboxOperationRequest,
    compiled_command_fingerprint,
    content_hash_bytes,
)
from src.sandbox.security import (
    SandboxPathError,
    normalize_virtual_path,
    redact_secrets,
    validate_secret_free_environment,
)

_BLOCKED_PROGRAMS = frozenset(
    {
        "bash",
        "curl",
        "docker",
        "mount",
        "nc",
        "netcat",
        "podman",
        "scp",
        "sh",
        "socat",
        "ssh",
        "su",
        "sudo",
        "umount",
        "wget",
    }
)
_ALLOWED_ENV_KEYS = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "MPLCONFIGDIR",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "WENJIN_TASK_SCRATCH",
        "WENJIN_WORKSPACE_ROOT",
    }
)


@dataclass(frozen=True, slots=True)
class CommandAuditPolicy:
    """Version-bound command compiler allowlist."""

    allowed_operations: frozenset[SandboxOperationKind] = field(
        default_factory=lambda: frozenset(
            {
                SandboxOperationKind.RUN_PYTHON,
                SandboxOperationKind.RUN_NOTEBOOK,
                SandboxOperationKind.SMOKE_CHECK,
            }
        )
    )
    compiler_fingerprints: dict[SandboxOperationKind, str] = field(default_factory=dict)
    allow_package_install: bool = False


class SandboxCommandAuditor:
    """Fail-closed validator for provider-bound argv metadata."""

    def __init__(self, policy: CommandAuditPolicy) -> None:
        self.policy = policy

    def audit(
        self,
        command: CompiledSandboxCommand,
        request: SandboxOperationRequest,
    ) -> CommandAuditEvidence:
        reasons: list[str] = []
        if command.operation != request.operation:
            reasons.append("operation_mismatch")
        if command.operation not in self.policy.allowed_operations:
            reasons.append("operation_not_allowed")
        expected_compiler = self.policy.compiler_fingerprints.get(command.operation)
        if expected_compiler is None or expected_compiler != command.compiler_fingerprint:
            reasons.append("compiler_not_allowlisted")
        if request.operation == SandboxOperationKind.INSTALL_DEPENDENCIES:
            if not self.policy.allow_package_install:
                reasons.append("dependency_install_not_allowed")
        try:
            validate_secret_free_environment(command.env)
        except ValueError:
            reasons.append("secret_environment_forbidden")
        if set(command.env).difference(_ALLOWED_ENV_KEYS):
            reasons.append("environment_key_not_allowed")
        _audit_command_shape(command, request, reasons)
        decision: Literal["allow", "deny"] = "deny" if reasons else "allow"
        return CommandAuditEvidence(
            decision=decision,
            risk_level="high" if reasons else "medium" if request.network_profile != SandboxNetworkProfile.NONE else "low",
            reasons=tuple(dict.fromkeys(reasons)),
            operation=command.operation,
            command_schema_version=command.schema_version,
            compiler_fingerprint=command.compiler_fingerprint,
            command_fingerprint=compiled_command_fingerprint(command),
            argv_preview=_safe_argv_preview(command.argv),
            cwd=command.cwd,
            env_keys=tuple(sorted(command.env)),
            network_profile=request.network_profile,
        )


def _audit_command_shape(
    command: CompiledSandboxCommand,
    request: SandboxOperationRequest,
    reasons: list[str],
) -> None:
    if not command.argv or len(command.argv) > 256:
        reasons.append("argv_invalid")
        return
    if any("\x00" in value or len(value) > 200_000 for value in (*command.argv, command.cwd)):
        reasons.append("command_payload_invalid")
    program = PurePosixPath(command.argv[0]).name.lower()
    if program in _BLOCKED_PROGRAMS:
        reasons.append("program_forbidden")
    _audit_cwd(command, request, reasons)
    operation = request.operation
    if operation == SandboxOperationKind.RUN_PYTHON:
        _audit_run_python(command, request, reasons)
    elif operation == SandboxOperationKind.RUN_NOTEBOOK:
        _audit_run_notebook(command, request, reasons)
    elif operation == SandboxOperationKind.SMOKE_CHECK:
        _audit_smoke_check(command, reasons)
    elif operation == SandboxOperationKind.INSTALL_DEPENDENCIES:
        _audit_install_dependencies(command, request, reasons)
    else:
        reasons.append("metadata_operation_has_no_provider_command")


def _audit_cwd(
    command: CompiledSandboxCommand,
    request: SandboxOperationRequest,
    reasons: list[str],
) -> None:
    if request.operation == SandboxOperationKind.INSTALL_DEPENDENCIES:
        if command.cwd != "/opt/wenjin/env":
            reasons.append("installer_cwd_invalid")
        return
    try:
        normalized = normalize_virtual_path(command.cwd)
    except SandboxPathError:
        reasons.append("cwd_outside_workspace")
        return
    if normalized != "/workspace" and not normalized.startswith("/workspace/tmp/"):
        reasons.append("operation_cwd_invalid")


def _audit_run_python(
    command: CompiledSandboxCommand,
    request: SandboxOperationRequest,
    reasons: list[str],
) -> None:
    operation_input = request.operation_input
    if operation_input.kind != SandboxOperationKind.RUN_PYTHON:
        reasons.append("input_kind_invalid")
        return
    if len(command.argv) != 2:
        reasons.append("run_python_argv_invalid")
        return
    if not _is_python_executable(command.argv[0]):
        reasons.append("python_executable_invalid")
    if command.argv[1] != operation_input.script_path:
        reasons.append("script_path_mismatch")


def _audit_run_notebook(
    command: CompiledSandboxCommand,
    request: SandboxOperationRequest,
    reasons: list[str],
) -> None:
    operation_input = request.operation_input
    if operation_input.kind != SandboxOperationKind.RUN_NOTEBOOK:
        reasons.append("input_kind_invalid")
        return
    expected = (
        command.argv[0],
        "-m",
        "jupyter",
        "nbconvert",
        "--execute",
        "--to",
        "notebook",
        "--output",
        operation_input.output_path,
        operation_input.notebook_path,
    )
    if not _is_python_executable(command.argv[0]) or command.argv != expected:
        reasons.append("run_notebook_argv_invalid")


def _audit_smoke_check(command: CompiledSandboxCommand, reasons: list[str]) -> None:
    if len(command.argv) != 3 or not _is_python_executable(command.argv[0]) or command.argv[1] != "-c":
        reasons.append("smoke_check_argv_invalid")
    elif content_hash_bytes(command.argv[2].encode()) != command.compiler_fingerprint:
        reasons.append("inline_program_mismatch")


def _audit_install_dependencies(
    command: CompiledSandboxCommand,
    request: SandboxOperationRequest,
    reasons: list[str],
) -> None:
    operation_input = request.operation_input
    if operation_input.kind != SandboxOperationKind.INSTALL_DEPENDENCIES:
        reasons.append("input_kind_invalid")
        return
    if len(command.argv) != 4 or not _is_python_executable(command.argv[0]):
        reasons.append("installer_argv_invalid")
        return
    if command.argv[1] != "-c":
        reasons.append("installer_argv_invalid")
    if content_hash_bytes(command.argv[2].encode()) != command.compiler_fingerprint:
        reasons.append("inline_program_mismatch")
    try:
        packages = tuple(json.loads(command.argv[3]))
    except (TypeError, ValueError):
        reasons.append("installer_packages_invalid")
        return
    if packages != operation_input.packages:
        reasons.append("installer_packages_mismatch")


def _is_python_executable(value: str) -> bool:
    return value in {"python3", "/opt/wenjin/env/venv/bin/python"}


def _safe_argv_preview(argv: tuple[str, ...]) -> tuple[str, ...]:
    preview: list[str] = []
    redact_next = False
    for index, raw in enumerate(argv[:32]):
        if redact_next:
            preview.append(f"<inline:{content_hash_bytes(raw.encode())}>")
            redact_next = False
            continue
        value = redact_secrets(raw)
        if value == "-c":
            preview.append(value)
            redact_next = True
            continue
        if index == 3 and len(value) > 200:
            preview.append(f"<payload:{content_hash_bytes(value.encode())}>")
        else:
            preview.append(value[:300])
    return tuple(preview)
