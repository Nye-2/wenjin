from __future__ import annotations

from src.agents.contracts.task_report import (
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    TaskReport,
)
from src.agents.harness.research_task_eval import evaluate_research_task_evidence


def _report(*, review_items: list[dict] | None = None, outputs: list | None = None) -> TaskReport:
    return TaskReport(
        execution_id="exec-eval-1",
        capability_id="sci_research_eval",
        status="completed",
        duration_seconds=3,
        narrative="Research task completed.",
        outputs=outputs or [],
        review_items=review_items or [],
        errors=[],
    )


def _node_metadata() -> list[dict]:
    return [
        {
            "node_type": "agent_invocation",
            "status": "completed",
            "node_metadata": {
                "template_id": "evidence_analyst.v1",
                "harness": {
                    "reproducibility_summary": {
                        "schema": "wenjin.harness.reproducibility_summary.v1",
                        "script_paths": ["/workspace/scripts/analysis.py"],
                        "dataset_paths": ["/workspace/datasets/panel.csv"],
                        "artifact_paths": ["/workspace/outputs/result.json"],
                    }
                },
            },
        },
        {
            "node_type": "agent_invocation",
            "status": "completed",
            "node_metadata": {
                "template_id": "literature_synthesizer.v1",
                "harness": {
                    "citation_source_audit": [
                        {
                            "schema": "wenjin.quality.citation_source_audit_finding.v1",
                            "risk": "low",
                            "source_id": "source-1",
                            "citation_key": "smith2024",
                        }
                    ]
                },
            },
        },
    ]


def test_research_task_eval_passes_when_literature_experiment_and_writing_are_reviewable() -> None:
    report = _report(
        outputs=[
            LibraryItemOutput(
                id="library-1",
                kind="library_item",
                preview="Smith 2024",
                data=LibraryItemData(
                    title="Federated LLM Evaluation",
                    authors=["Smith"],
                    year=2024,
                    source="semantic_scholar",
                    external_id="paper-1",
                    evidence_level="external_verified",
                ),
            ),
            DocumentOutput(
                id="doc-1",
                kind="document",
                preview="Manuscript revision note",
                data=DocumentData(
                    name="revision-note.md",
                    doc_kind="writing_review",
                    content="Use the verified experiment result and Smith 2024.",
                ),
            ),
        ],
        review_items=[
            {
                "id": "sandbox-review-1",
                "kind": "sandbox_artifact",
                "target": {
                    "path": "/workspace/outputs/result.json",
                    "artifact_kind": "sandbox_output",
                },
                "reproducibility": {
                    "source_task_id": "experiment_runner",
                    "sandbox_environment_id": "env-1",
                    "source_script": "/workspace/scripts/analysis.py",
                    "dataset_paths": ["/workspace/datasets/panel.csv"],
                    "content_hash": "sha256:result",
                },
            },
            {
                "id": "prism-review-1",
                "kind": "prism_file_change",
                "target": {
                    "logical_key": "section:introduction",
                    "file_path": "sections/introduction.tex",
                },
                "source": {
                    "execution_id": "exec-eval-1",
                    "task_id": "manuscript_writer",
                },
            },
        ],
    )

    evaluation = evaluate_research_task_evidence(
        report,
        node_events=_node_metadata(),
        required_surfaces=("literature", "experiment", "writing"),
    )

    assert evaluation.status == "pass"
    assert evaluation.coverage == {
        "literature": "pass",
        "experiment": "pass",
        "writing": "pass",
    }
    assert evaluation.findings == []
    assert evaluation.evidence["experiment"]["artifact_paths"] == ["/workspace/outputs/result.json"]


def test_research_task_eval_fails_missing_or_unreviewable_surfaces() -> None:
    report = _report(
        outputs=[
            LibraryItemOutput(
                id="library-1",
                kind="library_item",
                preview="Unverified paper",
                data=LibraryItemData(
                    title="Unverified Claim",
                    authors=["Unknown"],
                    year=2026,
                    source="manual",
                    evidence_level="metadata_only",
                ),
            ),
        ],
        review_items=[
            {
                "id": "sandbox-review-1",
                "kind": "sandbox_artifact",
                "target": {"path": "/workspace/outputs/result.json"},
                "reproducibility": {
                    "source_script": "/workspace/scripts/analysis.py",
                    "content_hash": "sha256:result",
                },
            }
        ],
    )

    evaluation = evaluate_research_task_evidence(
        report,
        node_events=[],
        required_surfaces=("literature", "experiment", "writing"),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {
        "literature": "fail",
        "experiment": "fail",
        "writing": "fail",
    }
    assert {finding["surface"] for finding in evaluation.findings} == {
        "literature",
        "experiment",
        "writing",
    }
    assert all("message" in finding for finding in evaluation.findings)


def test_research_task_eval_rejects_invalid_node_reproducibility_paths() -> None:
    report = _report(
        review_items=[
            {
                "id": "sandbox-review-1",
                "kind": "sandbox_artifact",
                "target": {"path": "/workspace/outputs/result.json"},
                "reproducibility": {
                    "source_script": "/workspace/scripts/analysis.py",
                    "dataset_paths": ["/workspace/datasets/panel.csv"],
                    "content_hash": "sha256:result",
                },
            }
        ],
    )
    node_events = [
        {
            "node_metadata": {
                "harness": {
                    "reproducibility_summary": {
                        "script_paths": ["/workspace/main/paper.tex"],
                        "dataset_paths": ["/workspace/datasets/panel.csv"],
                        "artifact_paths": ["/workspace/outputs/result.json"],
                    }
                }
            }
        }
    ]

    evaluation = evaluate_research_task_evidence(
        report,
        node_events=node_events,
        required_surfaces=("experiment",),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {"experiment": "fail"}
