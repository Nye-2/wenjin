"""ThreadData middleware - creates per-thread directories."""

from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class ThreadDataMiddleware(Middleware):
    """Creates workspace/uploads/outputs directories for each thread."""

    def __init__(self, base_dir: str | None = None, lazy_init: bool = True):
        self._base_dir = base_dir or ".academiagpt/threads"
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
        base = Path(self._base_dir) / thread_id / "user-data"

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
