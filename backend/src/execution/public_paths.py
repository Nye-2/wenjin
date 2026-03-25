"""Helpers for exposing sandbox execution outputs via public URLs."""

from __future__ import annotations

from pathlib import Path

from .path_utils import normalize_thread_id

_SANDBOX_VIRTUAL_PREFIX = "/mnt/user-data/"
_DEFAULT_PUBLIC_PREFIX = "/uploads/sandboxes"


def get_default_sandbox_dir() -> str:
    """Return the default sandbox dir used by execution services.

    In containerized deployments we prefer the shared uploads volume so
    generated artifacts can be served by nginx. In local development we fall
    back to a project-local uploads directory.
    """
    container_uploads = Path("/app/uploads")
    if container_uploads.exists():
        return str(container_uploads / "sandboxes")
    return str(Path.cwd() / "uploads" / "sandboxes")


def sandbox_path_to_public_url(
    sandbox_path: str | None,
    *,
    thread_id: str | None,
    public_prefix: str = _DEFAULT_PUBLIC_PREFIX,
) -> str | None:
    """Convert a virtual sandbox path to a public URL path.

    Example:
      /mnt/user-data/execution/latex_compile/123/main.pdf
      -> /uploads/sandboxes/default/execution/latex_compile/123/main.pdf
    """
    if not sandbox_path or not sandbox_path.startswith(_SANDBOX_VIRTUAL_PREFIX):
        return None

    relative_path = sandbox_path.removeprefix(_SANDBOX_VIRTUAL_PREFIX).lstrip("/")
    normalized_prefix = public_prefix.rstrip("/")
    normalized_thread_id = normalize_thread_id(thread_id)
    return f"{normalized_prefix}/{normalized_thread_id}/{relative_path}"
