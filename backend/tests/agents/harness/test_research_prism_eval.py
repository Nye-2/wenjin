from __future__ import annotations

from src.agents.contracts.task_report import TaskReport
from src.agents.harness.research_prism_eval import (
    writing_academic_style_evidence,
    writing_semantic_preservation_evidence,
)


def _report(review_items: list[dict]) -> TaskReport:
    return TaskReport(
        mission_id="exec-prism-eval",
        skill_id="sci_research_eval",
        status="completed",
        duration_seconds=1,
        narrative="done",
        outputs=[],
        review_items=review_items,
        errors=[],
    )


def test_prism_eval_builds_semantic_and_academic_style_evidence() -> None:
    report = _report(
        [
            {
                "id": "review-1",
                "kind": "prism_file_change",
                "target": {
                    "logical_key": "section:introduction",
                    "file_path": "sections/introduction.tex",
                },
                "preview": {
                    "content_contract": {
                        "latex_shape": "fragment",
                        "balanced_braces": True,
                    },
                    "semantic_contract": {
                        "risk": "low",
                        "preserves_claims": True,
                        "preserves_citations": True,
                        "has_equations": False,
                        "has_tables": False,
                    },
                    "academic_style_contract": {
                        "risk": "low",
                        "academic_style_score": 4,
                        "signals": ["hedged claims"],
                        "anti_patterns": [],
                    },
                },
            }
        ]
    )

    semantic = writing_semantic_preservation_evidence(report)
    style = writing_academic_style_evidence(report)

    assert semantic["review_item_count"] == 1
    assert semantic["checked_item_count"] == 1
    assert semantic["high_risk_count"] == 0
    assert style["review_item_count"] == 1
    assert style["min_academic_style_score"] == 4
    assert style["style_items"][0]["signals"] == ["hedged claims"]
