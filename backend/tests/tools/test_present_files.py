"""Tests for present_files tool path normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.builtins.artifacts import (
    VIRTUAL_OUTPUTS_PREFIX,
    _normalize_presented_filepath,
    present_files_tool,
)


def _config(thread_id: str = "thread-1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _state(outputs_dir: Path) -> dict:
    return {"thread_data": {"outputs_path": str(outputs_dir)}}


def test_normalizes_host_outputs_path(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    artifact_path = outputs_dir / "report.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("ok")

    normalized = _normalize_presented_filepath(
        str(artifact_path),
        outputs_dir=outputs_dir.resolve(),
    )

    assert normalized == f"{VIRTUAL_OUTPUTS_PREFIX}/report.md"


def test_keeps_virtual_outputs_path(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)

    normalized = _normalize_presented_filepath(
        f"{VIRTUAL_OUTPUTS_PREFIX}/summary.json",
        outputs_dir=outputs_dir.resolve(),
    )

    assert normalized == f"{VIRTUAL_OUTPUTS_PREFIX}/summary.json"


def test_accepts_relative_outputs_path(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)

    normalized = _normalize_presented_filepath(
        "outputs/figures/chart.png",
        outputs_dir=outputs_dir.resolve(),
    )

    assert normalized == f"{VIRTUAL_OUTPUTS_PREFIX}/figures/chart.png"


def test_rejects_paths_outside_outputs(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    workspace_dir = tmp_path / "threads" / "thread-1" / "user-data" / "workspace"
    outputs_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    leaked_path = workspace_dir / "notes.txt"
    leaked_path.write_text("secret")

    with pytest.raises(ValueError, match="Only files in /mnt/user-data/outputs"):
        _normalize_presented_filepath(
            str(leaked_path),
            outputs_dir=outputs_dir.resolve(),
        )


@pytest.mark.asyncio
async def test_present_files_tool_updates_artifacts_with_normalized_paths(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    artifact_path = outputs_dir / "drafts" / "paper.pdf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("pdf")

    result = await present_files_tool.coroutine(
        files=[str(artifact_path), "outputs/drafts/paper.pdf"],
        state=_state(outputs_dir),
        tool_call_id="tc-1",
        config=_config(),
    )

    assert result.update["artifacts"] == [f"{VIRTUAL_OUTPUTS_PREFIX}/drafts/paper.pdf"]
    tool_message = result.update["messages"][0]
    assert tool_message.tool_call_id == "tc-1"
    assert "Successfully presented 1 file(s)" in tool_message.content


@pytest.mark.asyncio
async def test_present_files_tool_returns_error_message_for_invalid_path(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)

    result = await present_files_tool.coroutine(
        files=["/tmp/not-allowed.txt"],
        state=_state(outputs_dir),
        tool_call_id="tc-2",
        config=_config(),
    )

    assert "artifacts" not in result.update
    assert result.update["messages"][0].content.startswith("Error: Only files in")
