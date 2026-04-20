"""Artifact presentation tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.agents.middlewares.thread_data import get_thread_data_root
from src.agents.thread_state import ThreadState

VIRTUAL_USER_DATA_PREFIX = "/mnt/user-data"
VIRTUAL_OUTPUTS_PREFIX = f"{VIRTUAL_USER_DATA_PREFIX}/outputs"


class PresentFilesInput(BaseModel):
    """Input for present_files."""

    files: list[str] = Field(description="List of file paths to present to the user")


def _resolve_outputs_dir(
    state: ThreadState,
    config: RunnableConfig,
) -> Path:
    """Resolve the current thread outputs directory."""
    thread_data = state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if outputs_path:
        return Path(outputs_path).expanduser().resolve()

    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")
    if not thread_id:
        raise ValueError("Thread outputs path is not available in runtime context.")

    return (get_thread_data_root(str(thread_id)) / "outputs").resolve()


def _normalize_presented_filepath(
    filepath: str,
    *,
    outputs_dir: Path,
) -> str:
    """Normalize a presented file path to `/mnt/user-data/outputs/*`."""
    raw_path = str(filepath or "").strip()
    if not raw_path:
        raise ValueError("Empty file path cannot be presented.")

    thread_root = outputs_dir.parent
    candidate: Path

    if raw_path.startswith(VIRTUAL_OUTPUTS_PREFIX):
        relative = raw_path.removeprefix(VIRTUAL_OUTPUTS_PREFIX).lstrip("/")
        candidate = outputs_dir / relative
    elif raw_path.startswith(f"{VIRTUAL_USER_DATA_PREFIX}/"):
        relative = raw_path.removeprefix(f"{VIRTUAL_USER_DATA_PREFIX}/").lstrip("/")
        candidate = thread_root / relative
    else:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            relative = raw_path.removeprefix("outputs/").lstrip("/")
            candidate = outputs_dir / relative

    resolved_path = candidate.resolve()

    try:
        relative_path = resolved_path.relative_to(outputs_dir)
    except ValueError as exc:
        raise ValueError(
            f"Only files in {VIRTUAL_OUTPUTS_PREFIX} can be presented: {raw_path}"
        ) from exc

    normalized = relative_path.as_posix()
    if not normalized or normalized == ".":
        raise ValueError(
            f"Only files in {VIRTUAL_OUTPUTS_PREFIX} can be presented: {raw_path}"
        )

    return f"{VIRTUAL_OUTPUTS_PREFIX}/{normalized}"


def build_presented_artifact_items(
    normalized_files: list[str],
    *,
    thread_id: str | None,
) -> list[dict[str, str]]:
    """Build structured file descriptors consumable by thread UI."""
    items: list[dict[str, str]] = []
    for virtual_path in normalized_files:
        normalized_virtual_path = (
            virtual_path
            if str(virtual_path).startswith("/")
            else f"/{str(virtual_path).lstrip('/')}"
        )
        item = {
            "name": Path(normalized_virtual_path).name,
            "path": normalized_virtual_path,
        }
        if thread_id:
            route_path = quote(normalized_virtual_path.lstrip("/"), safe="/")
            item["url"] = f"/api/threads/{thread_id}/artifacts/{route_path}"
            item["download_url"] = f"{item['url']}?download=true"
        items.append(item)
    return items


def build_presented_artifacts_block(
    items: list[dict[str, str]],
) -> dict[str, object]:
    """Build a thread block describing presented files."""
    return {
        "type": "artifacts",
        "title": "输出文件",
        "data": {"items": items},
    }


@tool("present_files", args_schema=PresentFilesInput)
async def present_files_tool(
    files: list[str],
    state: Annotated[ThreadState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command[Any]:
    """Present output files to the user.

    Use this tool to make generated files visible and downloadable for the user.
    Only files in the current thread's `/mnt/user-data/outputs` directory can be
    presented.
    """
    try:
        outputs_dir = _resolve_outputs_dir(state, config)
        normalized_files = list(
            dict.fromkeys(
                _normalize_presented_filepath(file_path, outputs_dir=outputs_dir)
                for file_path in files
            )
        )
    except ValueError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {exc}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    if not normalized_files:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Error: No valid output files to present. "
                            f"Only files in {VIRTUAL_OUTPUTS_PREFIX} can be presented."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    configurable = config.get("configurable", {})
    thread_id = str(configurable.get("thread_id") or "").strip() or None
    artifact_items = build_presented_artifact_items(
        normalized_files,
        thread_id=thread_id,
    )
    summary = "\n".join(f"- {path}" for path in normalized_files)
    return Command(
        update={
            "artifacts": normalized_files,
            "response_blocks": [build_presented_artifacts_block(artifact_items)],
            "response_metadata": {"artifacts": artifact_items},
            "messages": [
                ToolMessage(
                    content=(
                        f"Successfully presented {len(normalized_files)} file(s):\n"
                        f"{summary}"
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
