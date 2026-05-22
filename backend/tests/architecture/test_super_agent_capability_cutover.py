"""Architecture guard for Super Agent mission capability cutover."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

RUNTIME_FILES = [
    "backend/src/services/feature_action_resolution_service.py",
    "backend/src/services/dashboard_service.py",
    "backend/src/services/workspace_summary_service.py",
    "backend/src/task/runtime_blocks.py",
    "backend/src/application/presenters/agent_result_card.py",
    "backend/src/tools/builtins/launch_feature.py",
    "backend/src/agents/chat_agent/agent.py",
    "backend/src/compute/projection_service.py",
    "frontend/lib/workspace-feature-stages.ts",
]

OLD_WORKFLOW_IDS = {
    "deep_research",
    "opening_research",
    "literature_search",
    "literature_management",
    "paper_analysis",
    "literature_review",
    "framework_outline",
    "thesis_writing",
    "figure_generation",
    "proposal_outline",
    "background_research",
    "experiment_design",
    "patent_outline",
    "prior_art_search",
    "copyright_materials",
    "technical_description",
    "section_write",
    "section_revise",
}


def test_runtime_entrypoints_do_not_reference_old_workflow_ids() -> None:
    violations: list[str] = []
    for relative_path in RUNTIME_FILES:
        path = PROJECT_ROOT / relative_path
        text = path.read_text()
        for old_id in sorted(OLD_WORKFLOW_IDS):
            if old_id in text:
                violations.append(f"{relative_path}: {old_id}")

    assert violations == []
