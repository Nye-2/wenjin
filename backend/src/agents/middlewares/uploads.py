"""Uploads middleware - inject uploaded file context into the current user turn."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.middlewares.thread_data import get_thread_data_root
from src.agents.thread_state import ThreadState


class UploadsMiddleware(Middleware):
    """Tracks current-thread uploads and prepends them to the last HumanMessage."""

    @staticmethod
    def _normalize_uploaded_files(uploaded_files: list[dict] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in uploaded_files or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("filename") or "").strip()
            path = str(item.get("path") or "").strip()
            if not name or not path:
                continue
            normalized.append(
                {
                    "name": name,
                    "path": path,
                    "size": int(item.get("size") or item.get("size_bytes") or 0),
                    "kind": str(item.get("kind") or "transient"),
                }
            )
        return normalized

    @staticmethod
    def _render_uploaded_files_block(
        current_files: list[dict[str, Any]],
        historical_files: list[dict[str, Any]],
    ) -> str:
        lines = ["<uploaded_files>"]

        if current_files:
            lines.append("当前消息上传的文件:")
            for file_info in current_files:
                lines.append(
                    f"- {file_info['name']} [{file_info['kind']}] "
                    f"({file_info['size']} bytes): {file_info['path']}"
                )

        if historical_files:
            lines.append("此前上传且仍可使用的文件:")
            for file_info in historical_files:
                lines.append(
                    f"- {file_info['name']} [historical] "
                    f"({file_info['size']} bytes): {file_info['path']}"
                )

        lines.append(
            "文本文件可用 `read_file` 读取；图片可用 `view_image` 查看；需要向用户展示产物时使用 `present_files`。"
        )
        lines.append("</uploaded_files>")
        return "\n".join(lines)

    @staticmethod
    def _resolve_uploads_dir(
        state: ThreadState,
        config: RunnableConfig,
    ) -> Path | None:
        thread_data = state.get("thread_data") or {}
        uploads_path = thread_data.get("uploads_path")
        if uploads_path:
            return Path(uploads_path)

        thread_id = str(config.get("configurable", {}).get("thread_id") or "").strip()
        if not thread_id:
            return None
        return get_thread_data_root(thread_id) / "uploads"

    @staticmethod
    def _list_historical_files(
        uploads_dir: Path | None,
        *,
        current_names: set[str],
    ) -> list[dict[str, Any]]:
        if uploads_dir is None or not uploads_dir.exists():
            return []

        historical: list[dict[str, Any]] = []
        for file_path in sorted(uploads_dir.iterdir()):
            if not file_path.is_file() or file_path.name in current_names:
                continue
            historical.append(
                {
                    "name": file_path.name,
                    "path": f"/mnt/user-data/uploads/{file_path.name}",
                    "size": file_path.stat().st_size,
                }
            )
        return historical

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        current_files = self._normalize_uploaded_files(state.get("uploaded_files"))
        uploads_dir = self._resolve_uploads_dir(state, config)
        historical_files = self._list_historical_files(
            uploads_dir,
            current_names={file_info["name"] for file_info in current_files},
        )

        if not current_files and not historical_files:
            return {}

        messages = list(state.get("messages", []))
        if not messages:
            return {}

        last_human_idx = None
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                last_human_idx = index
                break

        if last_human_idx is None:
            return {}

        original = messages[last_human_idx]
        content = original.content if isinstance(original.content, str) else str(original.content)
        if "<uploaded_files>" in content:
            return {}

        file_listing = self._render_uploaded_files_block(current_files, historical_files)
        messages[last_human_idx] = HumanMessage(content=f"{file_listing}\n\n{content}")
        return {"messages": messages, "uploaded_files": current_files}
