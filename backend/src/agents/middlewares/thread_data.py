"""ThreadData middleware - creates per-thread directories."""

import shutil
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.execution.path_utils import normalize_thread_id

DEFAULT_THREAD_DATA_BASE_DIR = ".guanlan/threads"


def get_thread_data_root(
    thread_id: str | None,
    *,
    base_dir: str | None = None,
) -> Path:
    """Resolve the per-thread user-data root path."""
    safe_thread_id = normalize_thread_id(thread_id)
    return Path(base_dir or DEFAULT_THREAD_DATA_BASE_DIR) / safe_thread_id / "user-data"


def delete_thread_directory(
    thread_id: str | None,
    *,
    base_dir: str | None = None,
) -> Path:
    """Delete persisted filesystem data for a thread if it exists."""
    thread_dir = get_thread_data_root(thread_id, base_dir=base_dir).parent
    if thread_dir.exists():
        shutil.rmtree(thread_dir)
    return thread_dir


class ThreadDataMiddleware(Middleware):
    """Creates workspace/uploads/outputs directories for each thread."""

    position = "first"

    def __init__(self, base_dir: str | None = None, lazy_init: bool = True):
        self._base_dir = base_dir or DEFAULT_THREAD_DATA_BASE_DIR
        self._lazy_init = lazy_init

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        existing = state.get("thread_data")
        if existing and existing.get("workspace_path"):
            return {}

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        base = get_thread_data_root(thread_id, base_dir=self._base_dir)

        workspace_path = str(base / "workspace")
        uploads_path = str(base / "uploads")
        outputs_path = str(base / "outputs")

        if not self._lazy_init:
            for p in [workspace_path, uploads_path, outputs_path]:
                Path(p).mkdir(parents=True, exist_ok=True)

        return {
            "thread_data": {
                "workspace_path": workspace_path,
                "uploads_path": uploads_path,
                "outputs_path": outputs_path,
            }
        }
