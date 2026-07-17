"""Canonical filesystem paths for transient per-thread data."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.config import get_settings
from src.services.path_safety import normalize_path_component


def get_thread_data_root(
    thread_id: str | None,
    *,
    base_dir: str | None = None,
) -> Path:
    """Resolve the owned per-thread user-data root."""
    safe_thread_id = normalize_path_component(thread_id)
    root = Path(base_dir) if base_dir is not None else get_settings().thread_data_root
    return root / safe_thread_id / "user-data"


def delete_thread_directory(
    thread_id: str | None,
    *,
    base_dir: str | None = None,
) -> Path:
    """Delete one thread's transient filesystem directory if it exists."""
    thread_dir = get_thread_data_root(thread_id, base_dir=base_dir).parent
    if thread_dir.exists():
        shutil.rmtree(thread_dir)
    return thread_dir
