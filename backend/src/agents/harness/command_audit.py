"""Command audit contract for future sandbox command execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from src.sandbox.workspace_layout import WORKSPACE_ROOT

CommandAuditVerdict = Literal["pass", "warn", "block"]
CommandRiskLevel = Literal["low", "medium", "high"]

_SECRET_ENV_NAME_RE = re.compile(r"(api[_-]?key|secret|token|password|credential)", re.IGNORECASE)
_ABSOLUTE_PATH_FRAGMENT_RE = re.compile(r"(?<![A-Za-z0-9_.:/])(/(?!/)[^ \t\r\n'\"`|&;<>(),]*)")
_HIGH_RISK_SHELL_PATTERNS = (
    re.compile(r"\|\s*(ba)?sh\b"),
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    re.compile(r"base64\s+.*-d.*\|"),
    re.compile(r"/dev/tcp/"),
    re.compile(r"/proc/[^/]+/environ"),
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),
    re.compile(r"while\s+true.*&\s*done"),
)
_BLOCKED_PROGRAMS = frozenset(
    {
        "docker",
        "podman",
        "kubectl",
        "sudo",
        "su",
        "mount",
        "umount",
        "mkfs",
        "dd",
    }
)


@dataclass(frozen=True, slots=True)
class HarnessCommand:
    """Argv-first command request audited before execution."""

    argv: tuple[str, ...] = ()
    shell_command: str | None = None
    cwd: str = WORKSPACE_ROOT
    env: dict[str, str | None] = field(default_factory=dict)
    network_profile: str = "none"
    timeout_seconds: int | None = None
    output_bytes_cap: int | None = None


@dataclass(frozen=True, slots=True)
class CommandAuditPolicy:
    """Static policy used by command audit before runtime execution."""

    workspace_root: str = WORKSPACE_ROOT
    allow_shell: bool = False
    allow_package_install: bool = False
    allowed_network_profiles: tuple[str, ...] = ("none",)


@dataclass(frozen=True, slots=True)
class CommandAuditResult:
    """Structured command audit decision."""

    verdict: CommandAuditVerdict
    risk_level: CommandRiskLevel
    reasons: tuple[str, ...]
    command: HarnessCommand

    def model_dump(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "risk_level": self.risk_level,
            "reasons": list(self.reasons),
            "command": {
                "argv": list(self.command.argv),
                "shell_command": self.command.shell_command,
                "cwd": self.command.cwd,
                "env": _masked_env(self.command.env),
                "network_profile": self.command.network_profile,
                "timeout_seconds": self.command.timeout_seconds,
                "output_bytes_cap": self.command.output_bytes_cap,
            },
        }


def audit_command(
    command: HarnessCommand,
    policy: CommandAuditPolicy | None = None,
) -> CommandAuditResult:
    """Classify a sandbox command request without executing it."""

    effective_policy = policy or CommandAuditPolicy()
    reasons: list[str] = []
    warnings: list[str] = []

    if command.network_profile not in set(effective_policy.allowed_network_profiles):
        reasons.append("network_profile_not_allowed")

    if not _is_workspace_path(command.cwd, effective_policy.workspace_root):
        reasons.append("cwd_outside_workspace")

    if command.shell_command is not None:
        _audit_shell_command(command, effective_policy, reasons, warnings)
    else:
        _audit_argv(command, effective_policy, reasons, warnings)

    if reasons:
        return CommandAuditResult(
            verdict="block",
            risk_level="high",
            reasons=tuple(dict.fromkeys(reasons)),
            command=command,
        )
    if warnings:
        return CommandAuditResult(
            verdict="warn",
            risk_level="medium",
            reasons=tuple(dict.fromkeys(warnings)),
            command=command,
        )
    return CommandAuditResult(
        verdict="pass",
        risk_level="low",
        reasons=(),
        command=command,
    )


def _audit_shell_command(
    command: HarnessCommand,
    policy: CommandAuditPolicy,
    reasons: list[str],
    warnings: list[str],
) -> None:
    shell_command = str(command.shell_command or "")
    if not policy.allow_shell:
        reasons.append("shell_not_allowed")
    if command.argv:
        reasons.append("mixed_command_shape")
    normalized = " ".join(shell_command.split())
    if not normalized:
        reasons.append("shell_command_required")
    for pattern in _HIGH_RISK_SHELL_PATTERNS:
        if pattern.search(normalized):
            reasons.append("dangerous_shell_pattern")
            break
    if _looks_like_package_install_tokens(_split_shellish_tokens(normalized)):
        _audit_package_install(policy, reasons, warnings)
    for token in _split_shellish_tokens(normalized):
        _audit_path_token(token, policy, reasons)


def _audit_argv(
    command: HarnessCommand,
    policy: CommandAuditPolicy,
    reasons: list[str],
    warnings: list[str],
) -> None:
    if not command.argv:
        reasons.append("argv_required")
        return
    program = _program_name(command.argv[0])
    if program in _BLOCKED_PROGRAMS:
        reasons.append("blocked_program")
    if _looks_like_rm_rf_root(command.argv):
        reasons.append("dangerous_destructive_command")
    if _looks_like_package_install_tokens(command.argv):
        _audit_package_install(policy, reasons, warnings)
    for token in command.argv:
        _audit_path_token(token, policy, reasons)


def _audit_package_install(
    policy: CommandAuditPolicy,
    reasons: list[str],
    warnings: list[str],
) -> None:
    if not policy.allow_package_install:
        reasons.append("package_install_not_allowed")
        return
    warnings.append("package_install")


def _audit_path_token(token: str, policy: CommandAuditPolicy, reasons: list[str]) -> None:
    if token.startswith("/"):
        if not _is_workspace_path(token, policy.workspace_root):
            reasons.append("path_outside_workspace")
        return
    for match in _ABSOLUTE_PATH_FRAGMENT_RE.finditer(token):
        if not _is_workspace_path(match.group(1), policy.workspace_root):
            reasons.append("path_outside_workspace")
            return


def _is_workspace_path(path: str, workspace_root: str) -> bool:
    text = str(path or "").strip()
    if "\x00" in text:
        return False
    try:
        pure = PurePosixPath(text)
    except TypeError:
        return False
    if ".." in pure.parts:
        return False
    root = workspace_root.rstrip("/")
    normalized = pure.as_posix()
    return normalized == root or normalized.startswith(f"{root}/")


def _program_name(value: str) -> str:
    return PurePosixPath(str(value or "")).name


def _looks_like_rm_rf_root(argv: tuple[str, ...]) -> bool:
    if not argv or _program_name(argv[0]) != "rm":
        return False
    flags = [item for item in argv[1:] if item.startswith("-")]
    targets = [item for item in argv[1:] if not item.startswith("-")]
    recursive = any("r" in item for item in flags)
    force = any("f" in item for item in flags)
    destructive_targets = {"/", "/*", "~", "~/"}
    return recursive and force and any(item in destructive_targets for item in targets)


def _looks_like_package_install_tokens(tokens: tuple[str, ...]) -> bool:
    lowered = tuple(str(item).lower() for item in tokens)
    if "install" not in lowered:
        return False
    if lowered[:2] in {("pip", "install"), ("pip3", "install")}:
        return True
    for index in range(0, max(0, len(lowered) - 3)):
        if lowered[index + 1 : index + 4] == ("-m", "pip", "install"):
            return True
    return False


def _split_shellish_tokens(command: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[\s;&|]+", command) if part)


def _masked_env(env: dict[str, str | None]) -> dict[str, str | None]:
    masked: dict[str, str | None] = {}
    for key, value in env.items():
        masked[key] = "***" if _SECRET_ENV_NAME_RE.search(key) and value is not None else value
    return masked
