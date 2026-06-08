"""Command audit contract for future sandbox command execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from src.sandbox.workspace_layout import (
    WORKSPACE_ROOT,
    is_workspace_internal_path,
    is_workspace_protected_path,
)

CommandAuditVerdict = Literal["pass", "warn", "block"]
CommandRiskLevel = Literal["low", "medium", "high"]
CommandPolicyDecision = Literal["allow", "forbid"]

_SECRET_ENV_NAME_RE = re.compile(r"(api[_-]?key|secret|token|password|credential)", re.IGNORECASE)
_ABSOLUTE_PATH_FRAGMENT_RE = re.compile(r"(?<![A-Za-z0-9_.:/])(/(?!/)[^ \t\r\n'\"`|&;<>(),]*)")
_SAFE_PACKAGE_SPEC_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9_.!*+-]+)?$"
)
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
        "curl",
        "docker",
        "podman",
        "kubectl",
        "scp",
        "ssh",
        "sudo",
        "su",
        "mount",
        "umount",
        "mkfs",
        "dd",
        "wget",
    }
)
_PACKAGE_INSTALL_OPTION_ARITY = {
    "--cache-dir": 1,
    "--index-url": 1,
    "--extra-index-url": 1,
    "--trusted-host": 1,
    "--constraint": 1,
    "-c": 1,
    "--requirement": 1,
    "-r": 1,
}
_PACKAGE_INSTALL_FLAG_OPTIONS = frozenset(
    {
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        "--upgrade",
        "-U",
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
            "policy_decision": _policy_decision(self),
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


def require_command_policy_allowed(result: CommandAuditResult) -> None:
    """Raise if a command audit result is forbidden by policy."""

    decision = _policy_decision(result)
    if decision["decision"] != "allow":
        raise PermissionError(
            "sandbox command policy forbids execution: "
            f"{decision['reason']} ({decision['command_preview']})"
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
    shell_tokens = _split_shellish_tokens(normalized)
    if any(_program_name(token) in _BLOCKED_PROGRAMS for token in shell_tokens):
        reasons.append("blocked_program")
    if _looks_like_package_install_tokens(shell_tokens):
        _audit_package_install(policy, reasons, warnings)
        _audit_package_install_specs(shell_tokens, reasons)
    install_command = _looks_like_package_install_tokens(shell_tokens)
    for token in shell_tokens:
        _audit_path_token(token, policy, reasons, install_command=install_command)


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
    install_command = _looks_like_package_install_tokens(command.argv)
    if install_command:
        _audit_package_install(policy, reasons, warnings)
        _audit_package_install_specs(command.argv, reasons)
    for token in command.argv:
        _audit_path_token(token, policy, reasons, install_command=install_command)


def _audit_package_install(
    policy: CommandAuditPolicy,
    reasons: list[str],
    warnings: list[str],
) -> None:
    if not policy.allow_package_install:
        reasons.append("package_install_not_allowed")
        return
    warnings.append("package_install")


def _audit_package_install_specs(tokens: tuple[str, ...], reasons: list[str]) -> None:
    install_index = _package_install_index(tokens)
    if install_index is None:
        return
    package_tokens = _package_tokens_after_install(tokens, install_index + 1)
    if not package_tokens:
        reasons.append("unsafe_package_spec")
        return
    for package in package_tokens:
        if not _safe_package_spec(package):
            reasons.append("unsafe_package_spec")
            return


def _audit_path_token(
    token: str,
    policy: CommandAuditPolicy,
    reasons: list[str],
    *,
    install_command: bool = False,
) -> None:
    if token.startswith("/"):
        if not _is_workspace_path(token, policy.workspace_root):
            reasons.append("path_outside_workspace")
        elif _is_forbidden_workspace_path_token(token, install_command=install_command):
            reasons.append("protected_path")
        return
    for match in _ABSOLUTE_PATH_FRAGMENT_RE.finditer(token):
        if not _is_workspace_path(match.group(1), policy.workspace_root):
            reasons.append("path_outside_workspace")
            return
        if _is_forbidden_workspace_path_token(match.group(1), install_command=install_command):
            reasons.append("protected_path")
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
    return _package_install_index(lowered) is not None


def _package_install_index(tokens: tuple[str, ...]) -> int | None:
    lowered = tuple(str(item).lower() for item in tokens)
    if lowered[:2] in {("pip", "install"), ("pip3", "install")}:
        return 1
    for index in range(0, max(0, len(lowered) - 2)):
        if lowered[index : index + 3] == ("-m", "pip", "install"):
            return index + 2
    return None


def _package_tokens_after_install(tokens: tuple[str, ...], start_index: int) -> tuple[str, ...]:
    packages: list[str] = []
    index = start_index
    while index < len(tokens):
        token = str(tokens[index])
        if token in _PACKAGE_INSTALL_FLAG_OPTIONS:
            index += 1
            continue
        arity = _PACKAGE_INSTALL_OPTION_ARITY.get(token)
        if arity is not None:
            index += arity + 1
            continue
        if token.startswith("-"):
            reasons_token = token.split("=", 1)[0]
            if reasons_token in _PACKAGE_INSTALL_OPTION_ARITY:
                index += 1
                continue
            packages.append(token)
            index += 1
            continue
        packages.append(token)
        index += 1
    return tuple(packages)


def _safe_package_spec(value: str) -> bool:
    text = " ".join(str(value or "").strip().split())
    return bool(
        text
        and "://" not in text
        and not text.startswith(("-", ".", "/"))
        and "@" not in text
        and ";" not in text
        and not any(ch in text for ch in ("|", "&", "`", "$", "\\"))
        and _SAFE_PACKAGE_SPEC_RE.fullmatch(text)
    )


def _is_forbidden_workspace_path_token(path: str, *, install_command: bool) -> bool:
    if _is_allowed_runtime_path(path, install_command=install_command):
        return False
    return is_workspace_internal_path(path) or is_workspace_protected_path(path)


def _is_allowed_runtime_path(path: str, *, install_command: bool) -> bool:
    normalized = PurePosixPath(path).as_posix()
    if normalized.startswith("/workspace/.wenjin/env/python/"):
        return True
    if install_command and normalized == "/workspace/.wenjin/cache/pip":
        return True
    return False


def _policy_decision(result: CommandAuditResult) -> dict[str, str]:
    decision: CommandPolicyDecision = "forbid" if result.verdict == "block" else "allow"
    return {
        "schema": "wenjin.harness.command_policy_decision.v1",
        "decision": decision,
        "reason": _policy_reason(result),
        "command_preview": _command_preview(result.command),
    }


def _policy_reason(result: CommandAuditResult) -> str:
    reasons = set(result.reasons)
    if result.verdict == "block":
        if "unsafe_package_spec" in reasons:
            return "unsafe_package_spec"
        if "blocked_program" in reasons:
            return "program_forbidden"
        if "path_outside_workspace" in reasons or "cwd_outside_workspace" in reasons:
            return "host_path_forbidden"
        if "protected_path" in reasons:
            return "protected_path_forbidden"
        if "network_profile_not_allowed" in reasons:
            return "network_forbidden"
        if "package_install_not_allowed" in reasons:
            return "dependency_install_forbidden"
        if {"shell_not_allowed", "dangerous_shell_pattern", "mixed_command_shape"}.intersection(reasons):
            return "shell_forbidden"
        return "command_forbidden"
    if "package_install" in reasons:
        return "dependency_install"
    if _looks_like_workspace_python(result.command):
        return "workspace_python"
    return "workspace_command"


def _looks_like_workspace_python(command: HarnessCommand) -> bool:
    tokens = command.argv if command.argv else _split_shellish_tokens(command.shell_command or "")
    if not tokens:
        return False
    program = _program_name(tokens[0])
    if program.startswith("python"):
        return True
    if str(tokens[0]).startswith("/workspace/.wenjin/env/python/"):
        return True
    return any(str(token).startswith("/workspace/scripts/") and str(token).endswith(".py") for token in tokens)


def _command_preview(command: HarnessCommand) -> str:
    if command.shell_command is not None:
        preview = " ".join(str(command.shell_command or "").split())
    else:
        preview = " ".join(str(item) for item in command.argv)
    return preview if len(preview) <= 300 else f"{preview[:297]}..."


def _split_shellish_tokens(command: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[\s;&|]+", command) if part)


def _masked_env(env: dict[str, str | None]) -> dict[str, str | None]:
    masked: dict[str, str | None] = {}
    for key, value in env.items():
        masked[key] = "***" if _SECRET_ENV_NAME_RE.search(key) and value is not None else value
    return masked
