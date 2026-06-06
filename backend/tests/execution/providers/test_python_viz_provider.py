from __future__ import annotations

from pathlib import Path

import pytest

from src.execution.providers.python_viz import PythonVizProvider


def test_python_viz_build_command_uses_workspace_outputs_dir() -> None:
    provider = PythonVizProvider()
    command = provider.build_command("plt.plot([1, 2])", {})

    assert "/workspace/outputs" in " ".join(command)


@pytest.mark.asyncio
async def test_python_viz_process_result_reads_outputs_dir(tmp_path: Path) -> None:
    provider = PythonVizProvider()
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "plot.png").write_bytes(b"\x89PNG")

    result = await provider.process_result(
        exit_code=0,
        stdout="Done",
        stderr="",
        work_dir=str(tmp_path),
        options={"format": "png"},
    )

    assert result.success is True
    assert result.output_files == ["outputs/plot.png"]
