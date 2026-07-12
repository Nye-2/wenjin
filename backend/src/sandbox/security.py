"""Filesystem, egress and secret-safety helpers for sandbox operations."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlsplit

WORKSPACE_VIRTUAL_ROOT = PurePosixPath("/workspace")
PUBLIC_WORKSPACE_DIRS = ("main", "datasets", "scripts", "outputs", "reports")
ARTIFACT_ROOTS = ("outputs", "reports")
_PROTECTED_NAMES = frozenset({".git", ".hg", ".svn", ".wenjin", ".env"})
_PROTECTED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_METADATA_IPS = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{12,})\b"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|access[_-]?token|secret|password|credential)\s*[=:]\s*)"
        r"([^\s,;]+)"
    ),
)
_SECRET_ENV_NAME_RE = re.compile(
    r"(?ix)(?:^|[_-])(?:"
    r"api[_-]?key|access[_-]?(?:key|token)|secret(?:[_-]?(?:key|token))?|"
    r"password|passwd|credentials?|authorization|auth(?:[_-]?(?:key|token))?|"
    r"token|private[_-]?key|session[_-]?(?:key|token|cookie)"
    r")(?:$|[_-])"
)

SocketAddress = tuple[str, int] | tuple[str, int, int, int]
AddressInfo = tuple[int, int, int, str, SocketAddress]
HostResolver = Callable[[str, int], list[AddressInfo]]


class SandboxPathError(ValueError):
    """Raised when a virtual path escapes or targets protected state."""


class SandboxNetworkTargetError(ValueError):
    """Raised when an egress target resolves to a forbidden address."""


def normalize_virtual_path(path: str) -> str:
    text = str(path or "").strip()
    if not text or "\x00" in text:
        raise SandboxPathError("workspace path is empty or invalid")
    pure = PurePosixPath(text)
    if not pure.is_absolute() or ".." in pure.parts:
        raise SandboxPathError("workspace path must be absolute and cannot contain '..'")
    root_parts = WORKSPACE_VIRTUAL_ROOT.parts
    if pure.parts[: len(root_parts)] != root_parts:
        raise SandboxPathError("path is outside /workspace")
    normalized = pure.as_posix()
    if normalized != "/workspace" and not normalized.startswith("/workspace/"):
        raise SandboxPathError("path is outside /workspace")
    return normalized


def public_relative_path(path: str, *, allow_root: bool = False) -> PurePosixPath:
    normalized = normalize_virtual_path(path)
    pure = PurePosixPath(normalized)
    relative = PurePosixPath(*pure.parts[len(WORKSPACE_VIRTUAL_ROOT.parts) :])
    if not relative.parts:
        if allow_root:
            return relative
        raise SandboxPathError("workspace root is not a file target")
    if relative.parts[0] not in PUBLIC_WORKSPACE_DIRS and relative.parts[0] != "tmp":
        raise SandboxPathError("path is outside the public workspace contract")
    _reject_protected_parts(relative)
    return relative


def is_artifact_path(path: str) -> bool:
    try:
        relative = public_relative_path(path)
    except SandboxPathError:
        return False
    return bool(relative.parts and relative.parts[0] in ARTIFACT_ROOTS)


def is_dataset_path(path: str) -> bool:
    try:
        relative = public_relative_path(path)
    except SandboxPathError:
        return False
    return bool(relative.parts and relative.parts[0] == "datasets")


def is_script_path(path: str) -> bool:
    try:
        relative = public_relative_path(path)
    except SandboxPathError:
        return False
    return bool(relative.parts and relative.parts[0] == "scripts")


def resolve_public_host_path(public_root: Path, virtual_path: str) -> Path:
    """Resolve a public path while rejecting every existing symlink component."""

    relative = public_relative_path(virtual_path)
    root = public_root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SandboxPathError("symlink paths are not allowed in sandbox workspaces")
    resolved = current.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise SandboxPathError("resolved path escapes the public workspace")
    return current


def require_read_before_write(
    path: Path,
    *,
    expected_content_hash: str | None,
) -> None:
    if not path.exists():
        if expected_content_hash is not None:
            raise SandboxPathError("base content hash was supplied for a missing file")
        return
    if path.is_symlink() or not path.is_file():
        raise SandboxPathError("write target must be a regular public file")
    if expected_content_hash is None:
        raise SandboxPathError("existing files require a base content hash before write")
    actual = _content_hash_path(path)
    if actual != expected_content_hash:
        raise SandboxPathError("base content hash is stale")


def redact_secrets(value: str, *, known_values: Iterable[str] = ()) -> str:
    redacted = str(value or "")
    for known in sorted({item for item in known_values if len(item) >= 6}, key=len, reverse=True):
        redacted = redacted.replace(known, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def validate_secret_free_environment(env: dict[str, str]) -> None:
    for key in env:
        if _SECRET_ENV_NAME_RE.search(key):
            raise ValueError(f"secret-like environment variable is forbidden: {key}")


def is_forbidden_ip(address: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = ipaddress.ip_address(address) if isinstance(address, str) else address
    return bool(ip in _METADATA_IPS or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def validate_public_url(
    url: str,
    *,
    resolver: HostResolver = cast(HostResolver, socket.getaddrinfo),
    allowed_hosts: Iterable[str] = (),
) -> tuple[str, ...]:
    parsed = urlsplit(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SandboxNetworkTargetError("only absolute HTTP(S) URLs are allowed")
    host = parsed.hostname.rstrip(".").lower()
    allowed = {item.rstrip(".").lower() for item in allowed_hosts}
    if allowed and host not in allowed:
        raise SandboxNetworkTargetError("egress host is not allowlisted")
    if host in {"localhost", "metadata", "metadata.google.internal"}:
        raise SandboxNetworkTargetError("local or metadata host is forbidden")
    try:
        direct_ip = ipaddress.ip_address(host)
    except ValueError:
        direct_ip = None
    addresses: tuple[str, ...]
    if direct_ip is not None:
        addresses = (str(direct_ip),)
    else:
        try:
            resolved = resolver(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except OSError as exc:
            raise SandboxNetworkTargetError("egress host could not be resolved") from exc
        addresses = tuple(sorted({str(item[4][0]) for item in resolved if item[4]}))
    if not addresses or any(is_forbidden_ip(address) for address in addresses):
        raise SandboxNetworkTargetError("egress target resolves to a forbidden address")
    return addresses


def _reject_protected_parts(relative: PurePosixPath) -> None:
    for part in relative.parts:
        lowered = part.lower()
        if lowered in _PROTECTED_NAMES or lowered.startswith(".env."):
            raise SandboxPathError("protected workspace path")
        if lowered.endswith(_PROTECTED_SUFFIXES):
            raise SandboxPathError("secret-bearing file type is protected")


def _content_hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
