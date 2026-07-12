from __future__ import annotations

import socket

import pytest

from src.sandbox.security import (
    SandboxNetworkTargetError,
    SandboxPathError,
    is_forbidden_ip,
    normalize_virtual_path,
    redact_secrets,
    validate_public_url,
    validate_secret_free_environment,
)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.8",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.100.100.200",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_private_local_and_metadata_addresses_are_forbidden(address: str) -> None:
    assert is_forbidden_ip(address)


def test_public_url_revalidates_resolved_ip() -> None:
    def resolver(host: str, port: int):
        assert host == "packages.example.org"
        assert port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    addresses = validate_public_url(
        "https://packages.example.org/simple",
        resolver=resolver,
        allowed_hosts=("packages.example.org",),
    )

    assert addresses == ("93.184.216.34",)


def test_url_resolving_to_private_ip_is_rejected() -> None:
    def resolver(_host: str, port: int):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]

    with pytest.raises(SandboxNetworkTargetError, match="forbidden"):
        validate_public_url("http://metadata.example", resolver=resolver)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/workspace/../etc/passwd",
        "/workspace/.wenjin/manifest.json",
        "/workspace/main/.env",
        "/workspace/main/private.pem",
    ],
)
def test_protected_or_escape_paths_are_rejected(path: str) -> None:
    with pytest.raises(SandboxPathError):
        normalize_virtual_path(path) if not path.startswith("/workspace/") else _public_path(path)


def test_secret_redaction_covers_bearer_keys_and_assignments() -> None:
    raw = "Authorization: Bearer token-value\nOPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz\nGITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456\npassword=hunter2"

    redacted = redact_secrets(raw)

    assert "token-value" not in redacted
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("[REDACTED]") >= 3


@pytest.mark.parametrize(
    "key",
    [
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "SSH_PRIVATE_KEY",
        "SESSION_COOKIE",
    ],
)
def test_secret_like_environment_key_is_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="secret-like"):
        validate_secret_free_environment({key: "secret"})


def test_non_secret_runtime_environment_key_is_allowed() -> None:
    validate_secret_free_environment({"TOKENIZERS_PARALLELISM": "false"})


def _public_path(path: str) -> None:
    from src.sandbox.security import public_relative_path

    public_relative_path(path)
