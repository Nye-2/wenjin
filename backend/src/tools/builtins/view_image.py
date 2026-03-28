"""Image viewing tool for vision-capable chat models."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.agents.middlewares.thread_data import get_thread_data_root
from src.agents.thread_state import ThreadState

_VIRTUAL_USER_DATA_ROOT = "/mnt/user-data/"
_SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class ViewImageInput(BaseModel):
    """Input for view_image."""

    image_path: str = Field(
        description="Absolute sandbox path to the image file under /mnt/user-data/*",
    )


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _resolve_thread_virtual_path(
    *,
    thread_id: str | None,
    state: ThreadState,
    virtual_path: str,
) -> Path:
    normalized_path = f"/{str(virtual_path or '').lstrip('/')}"
    if not normalized_path.startswith(_VIRTUAL_USER_DATA_ROOT):
        raise ValueError(f"Image path must stay under {_VIRTUAL_USER_DATA_ROOT}: {virtual_path}")

    thread_data = state.get("thread_data") or {}
    workspace_path = thread_data.get("workspace_path")
    base_root = (
        Path(workspace_path).parent
        if isinstance(workspace_path, str) and workspace_path.strip()
        else get_thread_data_root(thread_id)
    )
    thread_root = base_root.resolve()
    relative = normalized_path.removeprefix(_VIRTUAL_USER_DATA_ROOT)
    candidate = (thread_root / relative).resolve()
    if not _is_within_root(candidate, thread_root):
        raise ValueError(f"Image path escapes the thread sandbox: {virtual_path}")
    return candidate


@tool("view_image", args_schema=ViewImageInput)
async def view_image_tool(
    image_path: str,
    state: Annotated[ThreadState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command[Any]:
    """Load one image file into thread state so a vision-capable model can inspect it."""
    configurable = config.get("configurable", {})
    thread_id = str(configurable.get("thread_id") or "").strip() or None

    try:
        actual_path = _resolve_thread_virtual_path(
            thread_id=thread_id,
            state=state,
            virtual_path=image_path,
        )
    except ValueError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(content=f"Error: {exc}", tool_call_id=tool_call_id),
                ]
            }
        )

    if not actual_path.is_file():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: Image file not found: {image_path}",
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )

    if actual_path.suffix.lower() not in _SUPPORTED_IMAGE_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_IMAGE_SUFFIXES))
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Error: Unsupported image format {actual_path.suffix or '(none)'}. "
                            f"Supported formats: {supported}"
                        ),
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )

    mime_type, _ = mimetypes.guess_type(actual_path.name)
    effective_mime = mime_type or "application/octet-stream"
    image_base64 = base64.b64encode(actual_path.read_bytes()).decode("utf-8")

    return Command(
        update={
            "viewed_images": {
                image_path: {
                    "base64": image_base64,
                    "mime_type": effective_mime,
                }
            },
            "messages": [
                ToolMessage(
                    content=f"Successfully loaded image for inspection: {image_path}",
                    tool_call_id=tool_call_id,
                ),
            ],
        }
    )
