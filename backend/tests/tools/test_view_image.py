"""Tests for the view_image tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.builtins.view_image import view_image_tool


def _config(thread_id: str = "thread-1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _state(workspace_dir: Path) -> dict:
    return {"thread_data": {"workspace_path": str(workspace_dir)}}


@pytest.mark.asyncio
async def test_view_image_tool_loads_image_into_viewed_images(tmp_path):
    workspace_dir = tmp_path / "threads" / "thread-1" / "user-data" / "workspace"
    uploads_dir = workspace_dir.parent / "uploads"
    uploads_dir.mkdir(parents=True)
    image_path = uploads_dir / "diagram.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    )

    result = await view_image_tool.coroutine(
        image_path="/mnt/user-data/uploads/diagram.png",
        state=_state(workspace_dir),
        tool_call_id="tc-1",
        config=_config(),
    )

    assert "/mnt/user-data/uploads/diagram.png" in result.update["viewed_images"]
    loaded = result.update["viewed_images"]["/mnt/user-data/uploads/diagram.png"]
    assert loaded["mime_type"] == "image/png"
    assert loaded["base64"]
    assert "Successfully loaded image" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_view_image_tool_rejects_unsupported_suffix(tmp_path):
    workspace_dir = tmp_path / "threads" / "thread-1" / "user-data" / "workspace"
    uploads_dir = workspace_dir.parent / "uploads"
    uploads_dir.mkdir(parents=True)
    bad_path = uploads_dir / "notes.txt"
    bad_path.write_text("not an image", encoding="utf-8")

    result = await view_image_tool.coroutine(
        image_path="/mnt/user-data/uploads/notes.txt",
        state=_state(workspace_dir),
        tool_call_id="tc-2",
        config=_config(),
    )

    assert "viewed_images" not in result.update
    assert "Unsupported image format" in result.update["messages"][0].content
