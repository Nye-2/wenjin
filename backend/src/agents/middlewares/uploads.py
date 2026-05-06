"""Uploads middleware - inject uploaded file context into the current user turn."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.middlewares.thread_data import get_thread_data_root
from src.agents.thread_state import ThreadState
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    resolve_workspace_upload_stored_path,
)

_MAX_EXCERPT_CHARS = 1600
_MAX_HISTORICAL_FILES = 10
_THREAD_VIRTUAL_ROOT = "/mnt/user-data"


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


class UploadsMiddleware(Middleware):
    """Tracks current-thread uploads and prepends them to the last HumanMessage."""

    @staticmethod
    def _normalize_uploaded_files(
        uploaded_files: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
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
                    "reference_id": str(item.get("reference_id") or "").strip() or None,
                    "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                }
            )
        return normalized

    @staticmethod
    def _read_markdown_excerpt(
        path: str,
        *,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        max_chars: int = _MAX_EXCERPT_CHARS,
    ) -> str | None:
        """Read a limited excerpt from a markdown file path.

        Handles both absolute paths and virtual reference paths by trying
        to resolve them against the thread data root or workspace upload root.
        """
        if not path or not isinstance(path, str):
            return None
        try:
            candidate = Path(path)
            if candidate.is_absolute() and candidate.exists():
                text = candidate.read_text(encoding="utf-8")
                return text[:max_chars] if len(text) <= max_chars else text[:max_chars] + "\n..."
        except Exception:
            pass

        normalized_path = f"/{path.lstrip('/')}"
        if thread_id and normalized_path.startswith(_THREAD_VIRTUAL_ROOT):
            try:
                thread_root = get_thread_data_root(thread_id).resolve()
                relative = normalized_path.removeprefix(_THREAD_VIRTUAL_ROOT).lstrip("/")
                candidate = (thread_root / relative).resolve()
                if _is_within_root(candidate, thread_root) and candidate.is_file():
                    text = candidate.read_text(encoding="utf-8")
                    return text[:max_chars] if len(text) <= max_chars else text[:max_chars] + "\n..."
            except Exception:
                pass

        if workspace_id:
            try:
                candidate = resolve_workspace_upload_stored_path(
                    workspace_id,
                    path,
                    root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                    allow_root_prefixed_relative=True,
                )
                if candidate.is_file():
                    text = candidate.read_text(encoding="utf-8")
                    return text[:max_chars] if len(text) <= max_chars else text[:max_chars] + "\n..."
            except Exception:
                pass
        return None

    @staticmethod
    def _render_uploaded_files_block(
        current_files: list[dict[str, Any]],
        historical_files: list[dict[str, Any]],
        *,
        thread_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        lines = ["<uploaded_files>"]

        if current_files:
            lines.append("当前消息上传的文件:")
            for file_info in current_files:
                lines.append(f"- {file_info['name']} [{file_info['kind']}] ({file_info['size']} bytes): {file_info['path']}")
                if file_info.get("kind") == "literature":
                    reference_id = file_info.get("reference_id")
                    if reference_id:
                        lines.append(f"  Reference Library ID: {reference_id}")
                    lines.append("  该文件的事实源是 Reference Library；请使用参考库目录/章节工具读取，不要直接引用上传文件名或 PDF 原文。")
                metadata = file_info.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                preprocess = metadata.get("preprocess")
                if not isinstance(preprocess, dict):
                    continue
                status = str(preprocess.get("status") or "").strip()
                provider = str(preprocess.get("provider") or "").strip()
                if status:
                    status_label = status
                    if provider:
                        status_label = f"{status} ({provider})"
                    lines.append(f"  预处理状态: {status_label}")
                if provider == "layout_parsing" and status == "succeeded":
                    if file_info.get("kind") == "literature":
                        lines.append("  该文献已建立结构化索引，请优先使用 `list_reference_library` 和 `read_reference_outline_node` 读取内容。")
                    else:
                        lines.append("  该文件已解析为结构化 Markdown，请使用 `read_file` 读取完整内容，不要直接臆测 PDF 内容。")
                elif provider == "image_vlm" and status == "succeeded":
                    lines.append("  该图片已通过 VLM 生成描述文本，请使用 `read_file` 读取完整内容。")
                markdown_paths = preprocess.get("markdown_paths")
                if isinstance(markdown_paths, list) and markdown_paths:
                    preview = ", ".join(str(p) for p in markdown_paths[:3] if isinstance(p, str))
                    if preview:
                        lines.append(f"  可读文本路径: {preview}")
                    # Add limited excerpt for first markdown file
                    for md_path in markdown_paths[:1]:
                        if not isinstance(md_path, str):
                            continue
                        excerpt = UploadsMiddleware._read_markdown_excerpt(
                            md_path,
                            thread_id=thread_id,
                            workspace_id=workspace_id,
                        )
                        if excerpt:
                            lines.append("  内容摘要:")
                            for excerpt_line in excerpt.splitlines():
                                lines.append(f"    {excerpt_line}")
                manifest_path = preprocess.get("manifest_path")
                if isinstance(manifest_path, str) and manifest_path.strip():
                    lines.append(f"  清单路径: {manifest_path}")
                error = preprocess.get("error")
                if isinstance(error, str) and error.strip():
                    lines.append(f"  错误信息: {error}")
                if status == "pending":
                    lines.append("  该文件正在后台解析，解析完成前不要引用或臆测 PDF 全文内容。")

        if historical_files:
            lines.append("此前上传且仍可使用的文件:")
            for file_info in historical_files:
                lines.append(f"- {file_info['name']} [historical] ({file_info['size']} bytes): {file_info['path']}")

        lines.append("文本文件可用 `read_file` 读取；图片可用 `view_image` 查看；文献内容以 Reference Library 为准；需要向用户展示产物时使用 `present_files`。")
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
        # Limit historical files to avoid prompt pollution
        return historical[:_MAX_HISTORICAL_FILES]

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

        configurable = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id") or state.get("thread_id") or "").strip() or None
        workspace_id = str(configurable.get("workspace_id") or state.get("workspace_id") or "").strip() or None
        file_listing = self._render_uploaded_files_block(
            current_files,
            historical_files,
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        messages[last_human_idx] = HumanMessage(content=f"{file_listing}\n\n{content}")
        return {"messages": messages, "uploaded_files": current_files}
