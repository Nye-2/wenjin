"""Runtime helpers for resolving the active sandbox provider and sandbox."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Final

from langchain_core.runnables import RunnableConfig

from src.config.config_loader import get_app_config
from src.reflection.resolvers import resolve_class
from src.sandbox import (
    DockerSandboxProvider,
    LocalSandboxProvider,
    Sandbox,
    SandboxProvider,
    get_sandbox_settings,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.agents.thread_state import ThreadState

_LOCAL_PROVIDER_PATH: Final[str] = "src.sandbox.providers.local:LocalSandboxProvider"
_DOCKER_PROVIDER_PATH: Final[str] = "src.sandbox.providers.docker:DockerSandboxProvider"
_PROVIDER_PATH_COMPAT: Final[dict[str, str]] = {
    "src.sandbox.local:LocalSandboxProvider": "src.sandbox.providers.local:LocalSandboxProvider",
    "src.sandbox.docker:DockerSandboxProvider": "src.sandbox.providers.docker:DockerSandboxProvider",
}

_provider_lock = threading.Lock()
_provider: SandboxProvider | None = None
_provider_initialized = False


def _normalize_provider_path(provider_path: str) -> str:
    """Translate legacy provider paths to the current module layout."""
    return _PROVIDER_PATH_COMPAT.get(provider_path, provider_path)


def _resolve_provider_path(provider_path: str | None) -> str | None:
    """Resolve the effective provider path from config + sandbox mode settings.

    Built-in local/docker providers can be switched via ``SANDBOX_MODE`` without
    editing ``config.yaml``. Custom provider paths remain authoritative.
    """
    settings = get_sandbox_settings()
    mode = getattr(settings, "mode", "local")
    normalized = _normalize_provider_path(provider_path) if provider_path else None
    builtin_paths = {_LOCAL_PROVIDER_PATH, _DOCKER_PROVIDER_PATH}

    if normalized is None or normalized in builtin_paths:
        return _DOCKER_PROVIDER_PATH if mode == "docker" else _LOCAL_PROVIDER_PATH

    return normalized


def _build_provider(provider_path: str) -> SandboxProvider:
    """Instantiate a sandbox provider from config."""
    provider_cls = resolve_class(
        _normalize_provider_path(provider_path),
        base_class=SandboxProvider,
    )

    if issubclass(provider_cls, LocalSandboxProvider):
        settings = get_sandbox_settings()
        return provider_cls(base_dir=settings.local.base_dir)

    if issubclass(provider_cls, DockerSandboxProvider):
        settings = get_sandbox_settings()
        return provider_cls(
            base_dir=settings.local.base_dir,
            image=settings.docker.image,
            timeout=settings.docker.timeout,
            memory=settings.docker.memory,
            cpu_limit=settings.docker.cpu_limit,
        )

    return provider_cls()


def get_sandbox_provider() -> SandboxProvider | None:
    """Return the process-wide sandbox provider if sandboxing is configured."""
    global _provider_initialized, _provider

    if _provider_initialized:
        return _provider

    with _provider_lock:
        if _provider_initialized:
            return _provider

        try:
            app_config = get_app_config()
            sandbox_config = getattr(app_config, "sandbox", None)
            provider_path = _resolve_provider_path(
                getattr(sandbox_config, "use", None) if sandbox_config else None
            )
            if provider_path:
                _provider = _build_provider(provider_path)
        except Exception as exc:
            logger.warning("Failed to initialize sandbox provider: %s", exc, exc_info=True)
            _provider = None
        finally:
            _provider_initialized = True

    return _provider


def reset_sandbox_provider() -> None:
    """Reset the cached sandbox provider for tests."""
    global _provider_initialized, _provider
    with _provider_lock:
        _provider = None
        _provider_initialized = False


async def resolve_runtime_sandbox(
    state: ThreadState | None,
    config: RunnableConfig | None,
) -> Sandbox:
    """Resolve the current thread sandbox from state or runtime config."""
    provider = get_sandbox_provider()
    if provider is None:
        raise RuntimeError("Sandbox provider is not configured.")

    runtime_config = config or {}
    configurable = runtime_config.get("configurable", {})
    sandbox_state = (state or {}).get("sandbox") or {}

    sandbox_id = sandbox_state.get("sandbox_id")
    if sandbox_id:
        sandbox = provider.get(str(sandbox_id))
        if sandbox is not None:
            return sandbox

    thread_id = configurable.get("thread_id") or sandbox_id
    if not thread_id:
        raise RuntimeError("Sandbox requires config.configurable.thread_id.")

    return await provider.acquire(str(thread_id))
