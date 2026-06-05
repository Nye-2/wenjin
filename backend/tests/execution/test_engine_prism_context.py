from __future__ import annotations

from src.agents.contracts.task_brief import TaskBrief
from src.execution.engine import ExecutionEngineV2


def test_engine_uses_explicit_latex_project_context_from_prism_launch_params():
    brief = TaskBrief(
        capability_id="prism_selection_optimize",
        raw_message="Prism 改稿",
        workspace_id="workspace-1",
        brief={
            "latex_project_id": "latex-1",
            "main_file": "paper.tex",
            "file_path": "sections/intro.tex",
        },
    )

    context = ExecutionEngineV2._explicit_manuscript_context_from_brief(brief)

    assert context == {
        "latex_project_id": "latex-1",
        "main_file": "paper.tex",
        "target_files": ["paper.tex", "sections/intro.tex"],
        "source": "explicit_launch_params",
    }
