from __future__ import annotations

from src.agents.contracts.task_report import (
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    TaskReport,
)
from src.agents.harness.research_task_eval_pack import (
    ResearchTaskEvalCase,
    evaluate_research_task_eval_pack,
)


def _report(*, outputs: list | None = None, review_items: list[dict] | None = None) -> TaskReport:
    return TaskReport(
        execution_id="exec-eval-pack",
        capability_id="sci_acceptance_case",
        status="completed",
        duration_seconds=5,
        narrative="Acceptance fixture.",
        outputs=outputs or [],
        review_items=review_items or [],
        errors=[],
    )


def test_research_task_eval_pack_groups_case_surface_failures() -> None:
    passing_case = ResearchTaskEvalCase(
        case_id="sci-lit-citation-pass",
        name="SCI literature citation support pass",
        workspace_type="sci",
        task_kind="literature_review",
        required_surfaces=("literature", "citation_strength", "paper_relevance"),
        report=_report(
            outputs=[
                LibraryItemOutput(
                    id="lib-1",
                    kind="library_item",
                    preview="Smith 2026",
                    data=LibraryItemData(
                        title="Federated Large Language Model Evaluation",
                        authors=["Smith"],
                        year=2026,
                        source="semantic_scholar",
                        external_id="paper-1",
                        evidence_level="external_verified",
                    ),
                ),
                DocumentOutput(
                    id="doc-1",
                    kind="document",
                    preview="review note",
                    data=DocumentData(
                        name="review.md",
                        doc_kind="writing_review",
                        content="Federated LLM evaluation is supported by Smith 2026.",
                    ),
                ),
            ]
        ),
        node_events=[
            {
                "node_type": "agent_invocation",
                "status": "completed",
                "node_metadata": {
                    "template_id": "literature_synthesizer.v1",
                    "harness": {
                        "citation_source_audit": [
                            {
                                "schema": "wenjin.quality.citation_source_audit_finding.v1",
                                "status": "verified",
                                "risk": "low",
                                "source_id": "source-1",
                                "citation_key": "smith2026",
                            }
                        ],
                        "paper_relevance_summary": {
                            "schema": "wenjin.harness.paper_relevance_summary.v1",
                            "aligned_count": 1,
                            "weak_count": 0,
                            "off_topic_count": 0,
                            "aligned_refs": [
                                {
                                    "source_id": "source-1",
                                    "citation_key": "smith2026",
                                    "reason": "directly studies federated LLM evaluation",
                                }
                            ],
                        },
                    },
                },
            }
        ],
    )
    failing_case = ResearchTaskEvalCase(
        case_id="sci-lit-citation-fail",
        name="SCI literature citation support fail",
        workspace_type="sci",
        task_kind="literature_review",
        required_surfaces=("literature", "citation_strength", "paper_relevance"),
        report=_report(),
        node_events=[
            {
                "node_type": "agent_invocation",
                "status": "completed",
                "node_metadata": {
                    "template_id": "literature_synthesizer.v1",
                    "harness": {
                        "paper_relevance_summary": {
                            "schema": "wenjin.harness.paper_relevance_summary.v1",
                            "aligned_count": 0,
                            "weak_count": 0,
                            "off_topic_count": 1,
                            "off_topic_refs": [{"citation_key": "soil2025"}],
                        },
                    },
                },
            }
        ],
    )

    result = evaluate_research_task_eval_pack([passing_case, failing_case])

    assert result.status == "fail"
    assert result.case_count == 2
    assert result.pass_count == 1
    assert result.fail_count == 1
    assert result.case_results["sci-lit-citation-pass"].status == "pass"
    assert result.case_results["sci-lit-citation-fail"].coverage == {
        "literature": "fail",
        "citation_strength": "fail",
        "paper_relevance": "fail",
    }
    assert result.failed_cases == [
        {
            "case_id": "sci-lit-citation-fail",
            "name": "SCI literature citation support fail",
            "workspace_type": "sci",
            "task_kind": "literature_review",
            "failed_surfaces": ["literature", "citation_strength", "paper_relevance"],
        }
    ]
    assert result.surface_failures == {
        "literature": ["sci-lit-citation-fail"],
        "citation_strength": ["sci-lit-citation-fail"],
        "paper_relevance": ["sci-lit-citation-fail"],
    }


def test_research_task_eval_pack_rejects_duplicate_case_ids() -> None:
    case = ResearchTaskEvalCase(
        case_id="duplicate-case",
        name="Duplicate",
        workspace_type="sci",
        task_kind="literature_review",
        required_surfaces=("literature",),
        report=_report(),
    )

    try:
        evaluate_research_task_eval_pack([case, case])
    except ValueError as exc:
        assert "duplicate research eval case id" in str(exc)
        assert "duplicate-case" in str(exc)
    else:
        raise AssertionError("duplicate case ids should fail fast")
