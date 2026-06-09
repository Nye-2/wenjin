from __future__ import annotations

from collections import Counter

from src.agents.contracts.task_report import (
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    TaskReport,
)
from src.agents.harness.research_task_eval import evaluate_research_task_evidence
from src.agents.lead_agent.v2.team.contracts import AgentInvocation, CapabilityTeamPolicy
from src.agents.lead_agent.v2.team.quality_gates import evaluate_quality_gates


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


def _team_invocation(
    *,
    template_id: str = "citation_auditor.v1",
    output_report: dict,
    quality_contract: dict,
) -> AgentInvocation:
    return AgentInvocation(
        id=f"team.1.{template_id.replace('.', '_')}.1",
        iteration=1,
        template_id=template_id,
        display_name="引文审计员",
        assigned_role="引文审计员",
        recruitment_reason="test",
        input_brief={"quality_contract": quality_contract},
        status="succeeded",
        output_report=output_report,
    )


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
                "preview": {
                    "content_contract": {
                        "path": "sections/introduction.tex",
                        "content_format": "latex_fragment",
                        "latex_shape": "fragment",
                        "balanced_braces": True,
                    }
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


def test_research_task_eval_rejects_main_tex_prism_change_without_complete_latex_contract() -> None:
    report = _report(
        review_items=[
            {
                "id": "prism-review-1",
                "kind": "prism_file_change",
                "target": {
                    "logical_key": "project:main",
                    "file_path": "main.tex",
                },
                "preview": {
                    "content_contract": {
                        "path": "main.tex",
                        "content_format": "latex_fragment",
                        "latex_shape": "fragment",
                        "balanced_braces": True,
                    }
                },
                "source": {
                    "execution_id": "exec-eval-1",
                    "task_id": "manuscript_writer",
                },
            }
        ],
    )

    evaluation = evaluate_research_task_evidence(
        report,
        required_surfaces=("writing",),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {"writing": "fail"}
    assert evaluation.findings == [
        {
            "surface": "writing",
            "severity": "high",
            "message": "No structurally reviewable Prism file-change or document output was produced for writing review.",
        }
    ]


def test_research_task_eval_accepts_team_quality_gate_citation_refs() -> None:
    report = _report()
    quality_contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "citation_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["claim_source_binding_checked"],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }
    gates = evaluate_quality_gates(
        ["claim_source_binding_checked"],
        [
            _team_invocation(
                quality_contract=quality_contract,
                output_report={
                    "text": "Citation audit complete.",
                    "quality_gates_checked": ["claim_source_binding_checked"],
                    "citation_key_audit": [
                        {
                            "citation_key": "smith2026",
                            "source_id": "source-1",
                            "status": "weak",
                            "claim": "The central claim has partial support.",
                        },
                        {
                            "citation_key": "smith2026",
                            "source_id": "source-1",
                            "status": "fabricated",
                            "claim": "This should not be trusted as literature evidence.",
                        },
                    ],
                    "missing_sources": [],
                },
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
        latest_invocations=[],
    )
    node_events = [
        {
            "node_type": "team_quality_gate",
            "status": "completed",
            "runtime_state": {
                "quality_gates": [gate.model_dump(mode="json") for gate in gates]
            },
        }
    ]

    evaluation = evaluate_research_task_evidence(
        report,
        node_events=node_events,
        required_surfaces=("literature",),
    )

    assert evaluation.status == "pass"
    assert evaluation.coverage == {"literature": "pass"}
    assert evaluation.evidence["literature"]["citation_audit_refs"] == [
        {
            "source_id": "source-1",
            "citation_key": "smith2026",
            "risk": "weak",
        }
    ]


def test_research_task_eval_passes_workflow_trace_from_member_transcripts() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_metadata": {
                    "harness": {
                        "member_execution_transcript": {
                            "schema": "wenjin.harness.member_execution_transcript.v1",
                            "tool_call_count": 2,
                            "tool_names": ["library_read", "citation_parser"],
                            "completed_tool_count": 2,
                            "failed_tool_count": 0,
                            "usage": {"input_tokens": 400, "output_tokens": 120, "total_tokens": 520},
                        }
                    }
                }
            },
            {
                "node_metadata": {
                    "harness": {
                        "member_execution_transcript": {
                            "schema": "wenjin.harness.member_execution_transcript.v1",
                            "tool_call_count": 1,
                            "tool_names": ["sandbox.run_python"],
                            "completed_tool_count": 1,
                            "failed_tool_count": 0,
                            "changed_paths": ["/workspace/reports/experiment.md"],
                            "sandbox_job_ids": ["job-1"],
                            "sandbox_environment_ids": ["env-1"],
                            "scratch_refs": ["/workspace/tmp/tasks/exec-1/experiment_runner"],
                            "generated_artifact_count": 1,
                            "billing": {"credits_charged": 1},
                            "duration_ms": 1500,
                        }
                    }
                }
            },
        ],
        required_surfaces=("workflow_trace",),
    )

    assert evaluation.status == "pass"
    assert evaluation.coverage == {"workflow_trace": "pass"}
    assert evaluation.findings == []
    assert evaluation.evidence["workflow_trace"] == {
        "member_count": 2,
        "tool_call_count": 3,
        "completed_tool_count": 3,
        "failed_tool_count": 0,
        "tool_names": ["library_read", "citation_parser", "sandbox.run_python"],
        "changed_paths": ["/workspace/reports/experiment.md"],
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "scratch_refs": ["/workspace/tmp/tasks/exec-1/experiment_runner"],
        "generated_artifact_count": 1,
        "usage": {"input_tokens": 400, "output_tokens": 120, "total_tokens": 520},
        "billing": {"credits_charged": 1},
        "duration_ms": 1500,
    }


def test_research_task_eval_fails_workflow_trace_without_member_transcripts() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_metadata": {
                    "harness": {
                        "run_journal_summary": {
                            "schema": "wenjin.harness.run_journal_summary.v1",
                            "summary": "已完成实验",
                        }
                    }
                }
            }
        ],
        required_surfaces=("workflow_trace",),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {"workflow_trace": "fail"}
    assert evaluation.findings == [
        {
            "surface": "workflow_trace",
            "severity": "high",
            "message": "No member execution transcript with completed tool activity was produced.",
        }
    ]
    assert evaluation.evidence["workflow_trace"] == {
        "member_count": 0,
        "tool_call_count": 0,
        "completed_tool_count": 0,
        "failed_tool_count": 0,
        "tool_names": [],
        "changed_paths": [],
        "sandbox_job_ids": [],
        "sandbox_environment_ids": [],
        "scratch_refs": [],
        "generated_artifact_count": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "billing": {"credits_charged": 0},
        "duration_ms": 0,
    }
