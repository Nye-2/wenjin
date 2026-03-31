"""Tests for sandbox runtime provider selection."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.sandbox.providers.docker import DockerSandboxProvider
from src.sandbox.providers.local import LocalSandboxProvider
from src.sandbox.runtime import (
    _DOCKER_PROVIDER_PATH,
    _LOCAL_PROVIDER_PATH,
    _resolve_provider_path,
    get_sandbox_provider,
    reset_sandbox_provider,
)


def _settings(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        mode=mode,
        local=SimpleNamespace(base_dir=".wenjin/threads"),
        docker=SimpleNamespace(
            image="wenjin/sandbox:latest",
            timeout=300,
            memory="1g",
            cpu_limit=2,
        ),
    )


def test_resolve_provider_path_defaults_to_local_mode():
    with patch("src.sandbox.runtime.get_sandbox_settings", return_value=_settings("local")):
        assert _resolve_provider_path(None) == _LOCAL_PROVIDER_PATH


def test_resolve_provider_path_promotes_builtin_provider_to_docker_mode():
    with patch("src.sandbox.runtime.get_sandbox_settings", return_value=_settings("docker")):
        assert _resolve_provider_path(_LOCAL_PROVIDER_PATH) == _DOCKER_PROVIDER_PATH
        assert _resolve_provider_path(_DOCKER_PROVIDER_PATH) == _DOCKER_PROVIDER_PATH


def test_resolve_provider_path_preserves_custom_provider():
    custom_path = "custom.module:SandboxProvider"
    with patch("src.sandbox.runtime.get_sandbox_settings", return_value=_settings("docker")):
        assert _resolve_provider_path(custom_path) == custom_path


def test_get_sandbox_provider_uses_docker_provider_when_mode_is_docker():
    reset_sandbox_provider()
    app_config = SimpleNamespace(sandbox=SimpleNamespace(use=_LOCAL_PROVIDER_PATH))

    try:
        with patch("src.sandbox.runtime.get_app_config", return_value=app_config), patch(
            "src.sandbox.runtime.get_sandbox_settings",
            return_value=_settings("docker"),
        ):
            provider = get_sandbox_provider()

        assert isinstance(provider, DockerSandboxProvider)
    finally:
        reset_sandbox_provider()


def test_get_sandbox_provider_uses_local_provider_when_mode_is_local():
    reset_sandbox_provider()
    app_config = SimpleNamespace(sandbox=SimpleNamespace(use=_DOCKER_PROVIDER_PATH))

    try:
        with patch("src.sandbox.runtime.get_app_config", return_value=app_config), patch(
            "src.sandbox.runtime.get_sandbox_settings",
            return_value=_settings("local"),
        ):
            provider = get_sandbox_provider()

        assert isinstance(provider, LocalSandboxProvider)
    finally:
        reset_sandbox_provider()


def test_get_sandbox_provider_rejects_legacy_provider_path():
    reset_sandbox_provider()
    app_config = SimpleNamespace(sandbox=SimpleNamespace(use="src.sandbox.local:LocalSandboxProvider"))

    try:
        with patch("src.sandbox.runtime.get_app_config", return_value=app_config), patch(
            "src.sandbox.runtime.get_sandbox_settings",
            return_value=_settings("local"),
        ):
            with pytest.raises(ImportError, match="Missing dependency 'src'"):
                get_sandbox_provider()
    finally:
        reset_sandbox_provider()
