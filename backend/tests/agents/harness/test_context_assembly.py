from __future__ import annotations

import json

import src.agents.harness.context_assembly as context_assembly
from src.agents.harness.context_assembly import (
    build_harness_context_bundle,
    render_harness_context_for_prompt,
)


def test_harness_context_bundle_contains_sandbox_contract_and_execution_evidence() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "run experiment", "topic": "federated LLM"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-1",
                        "display_name": "实验复核",
                        "status": "completed",
                        "summary": "已有实验代码位于 sandbox。",
                        "node_metadata": {
                            "harness": {
                                "sandbox_execution_summary": {
                                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                                    "python_runs": 1,
                                    "failed_python_runs": 0,
                                    "recoverable_failures": 0,
                                },
                                "reproducibility_summary": {
                                    "schema": "wenjin.harness.reproducibility_summary.v1",
                                    "python_runs": 1,
                                    "manifest_count": 1,
                                    "script_paths": ["/workspace/scripts/analysis.py"],
                                    "artifact_paths": ["/workspace/reports/analysis.md"],
                                    "dependency_names": ["pandas"],
                                },
                                "experiment_interpretation_summary": {
                                    "schema": "wenjin.harness.experiment_interpretation_summary.v1",
                                    "interpretation_count": 1,
                                    "method_summary_count": 1,
                                    "metric_names": ["accuracy"],
                                    "verified_result_count": 1,
                                    "limitation_count": 1,
                                    "artifact_paths": ["/workspace/reports/analysis.md"],
                                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                                },
                                "statistical_robustness_summary": {
                                    "schema": "wenjin.harness.statistical_robustness_summary.v1",
                                    "check_count": 1,
                                    "method_count": 1,
                                    "metric_names": ["accuracy"],
                                    "sample_size_count": 1,
                                    "sample_sizes": [1250],
                                    "robustness_check_count": 2,
                                    "passed_robustness_check_count": 2,
                                    "failed_robustness_check_count": 0,
                                    "critical_failed_robustness_check_count": 0,
                                    "limitation_count": 1,
                                    "artifact_paths": ["/workspace/reports/analysis.md"],
                                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                                },
                            }
                        },
                    }
                ]
            }
        },
        max_chars=12000,
    )

    assert bundle["schema"] == "wenjin.harness.context_bundle.v1"
    assert bundle["workspace_id"] == "ws-1"
    assert bundle["workspace_type"] == "sci"
    assert bundle["task"] == {"goal": "run experiment", "topic": "federated LLM"}
    assert bundle["sandbox"]["root"] == "/workspace"
    assert "/workspace/scripts" in bundle["sandbox"]["standard_dirs"]
    assert "/workspace/outputs" in bundle["sandbox"]["artifact_roots"]
    assert bundle["sandbox"]["datasets_manifest_path"] == "/workspace/datasets/manifest.json"
    assert bundle["sandbox"]["artifacts_manifest_path"] == "/workspace/reports/artifacts.json"
    assert bundle["sandbox"]["task_scratch_root"] == "/workspace/tmp/tasks"
    assert bundle["sandbox"]["workspace_profile"]["workspace_type"] == "sci"
    assert bundle["sandbox"]["workspace_profile"]["primary_files"] == [
        "/workspace/main/main.tex",
        "/workspace/main/refs.bib",
        "/workspace/main/README.md",
    ]
    assert "/workspace/reports/experiment-report.md" in bundle["sandbox"]["workspace_profile"]["report_paths"]
    assert bundle["sandbox"]["path_classes"]["artifacts"] == [
        "/workspace/outputs",
        "/workspace/reports",
    ]
    assert bundle["sandbox"]["path_classes"]["scratch"] == ["/workspace/tmp"]
    assert bundle["sandbox"]["path_classes"]["task_scratch"] == ["/workspace/tmp/tasks"]
    assert "/workspace/outputs/README.md" in bundle["sandbox"]["guidance_paths"]
    assert "/workspace/reports/artifacts.json" in bundle["sandbox"]["guidance_paths"]
    assert bundle["sandbox"]["operation_policy"]["direct_write_tools"]["tools"] == [
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.apply_patch",
    ]
    assert bundle["sandbox"]["operation_policy"]["direct_write_tools"]["allowed_root_files"] == [
        "/workspace/*",
    ]
    assert bundle["sandbox"]["operation_policy"]["direct_write_tools"]["denied_path_classes"] == [
        "protected",
        "internal",
        "guidance",
    ]
    assert bundle["sandbox"]["operation_policy"]["manifest_update_tools"]["sandbox.register_dataset"] == {
        "manifest_path": "/workspace/datasets/manifest.json",
        "allowed_roots": ["/workspace/datasets"],
    }
    assert "**/.env" in bundle["sandbox"]["protected_paths"]
    assert "/workspace/tmp/tasks/.harness/**" in bundle["sandbox"]["internal_paths"]
    assert "node_modules" in bundle["sandbox"]["search_ignored_names"]
    assert "__pycache__" in bundle["sandbox"]["search_ignored_names"]
    assert bundle["recent_execution_evidence"] == [
        {
            "execution_id": "exec-1",
            "display_name": "实验复核",
            "status": "completed",
            "summary": "已有实验代码位于 sandbox。",
            "harness": {
                "sandbox_execution_summary": {
                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                    "python_runs": 1,
                    "failed_python_runs": 0,
                    "recoverable_failures": 0,
                },
                "reproducibility_summary": {
                    "schema": "wenjin.harness.reproducibility_summary.v1",
                    "python_runs": 1,
                    "manifest_count": 1,
                    "script_paths": ["/workspace/scripts/analysis.py"],
                    "artifact_paths": ["/workspace/reports/analysis.md"],
                    "dependency_names": ["pandas"],
                },
                "experiment_interpretation_summary": {
                    "schema": "wenjin.harness.experiment_interpretation_summary.v1",
                    "interpretation_count": 1,
                    "method_summary_count": 1,
                    "metric_names": ["accuracy"],
                    "verified_result_count": 1,
                    "limitation_count": 1,
                    "artifact_paths": ["/workspace/reports/analysis.md"],
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                },
                "statistical_robustness_summary": {
                    "schema": "wenjin.harness.statistical_robustness_summary.v1",
                    "check_count": 1,
                    "method_count": 1,
                    "metric_names": ["accuracy"],
                    "sample_size_count": 1,
                    "sample_sizes": [1250],
                    "robustness_check_count": 2,
                    "passed_robustness_check_count": 2,
                    "failed_robustness_check_count": 0,
                    "critical_failed_robustness_check_count": 0,
                    "limitation_count": 1,
                    "artifact_paths": ["/workspace/reports/analysis.md"],
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                },
            },
        }
    ]
    assert bundle["experiment_interpretation_summary"] == {
        "schema": "wenjin.harness.experiment_interpretation_summary.v1",
        "interpretation_count": 1,
        "method_summary_count": 1,
        "metric_names": ["accuracy"],
        "verified_result_count": 1,
        "limitation_count": 1,
        "artifact_paths": ["/workspace/reports/analysis.md"],
        "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
    }
    assert bundle["statistical_robustness_summary"] == {
        "schema": "wenjin.harness.statistical_robustness_summary.v1",
        "check_count": 1,
        "method_count": 1,
        "metric_names": ["accuracy"],
        "sample_size_count": 1,
        "sample_sizes": [1250],
        "robustness_check_count": 2,
        "passed_robustness_check_count": 2,
        "failed_robustness_check_count": 0,
        "critical_failed_robustness_check_count": 0,
        "limitation_count": 1,
        "artifact_paths": ["/workspace/reports/analysis.md"],
        "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
    }
    assert bundle["budget"] == {"max_chars": 12000, "truncated": False}


def test_harness_context_bundle_exposes_team_member_execution_package() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={
            "execution_id": "exec-1",
            "node_id": "research_scout.v1__1",
            "prompt": "continue the experiment",
            "inputs": {
                "capability_goal": "produce_workspace_review_package",
                "team_role": "实验工程师",
                "team_blackboard": {
                    "harness_replan_signals": [
                        {
                            "schema": "wenjin.harness.replan_signal.v1",
                            "trigger": "recoverable_python_failure",
                            "failure_codes": ["python_exit_nonzero"],
                            "recommended_action": "revise_code_same_member",
                        }
                    ]
                },
                "upstream_context": {
                    "artifact_candidates": [
                        {
                            "path": "/workspace/reports/model-eval.md",
                            "kind": "sandbox_report",
                            "title": "Model evaluation",
                        },
                        {
                            "path": "/workspace/tmp/tasks/.harness/outputs/exec/node/stdout.txt",
                            "kind": "debug",
                        },
                    ]
                },
            },
        },
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-1",
                        "node_metadata": {
                            "harness": {
                                "file_change_summary": {
                                    "schema": "wenjin.harness.file_change_summary.v1",
                                    "changed_paths": ["/workspace/main/paper.tex"],
                                },
                                "sandbox_execution_summary": {
                                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                                    "python_runs": 1,
                                    "sandbox_job_ids": ["job-1"],
                                    "execution_lifecycle_count": 1,
                                    "job_statuses": ["succeeded"],
                                    "exit_codes": [0],
                                    "output_refs": [
                                        "/workspace/tmp/tasks/.harness/outputs/exec-1/research_scout/stdout.txt"
                                    ],
                                },
                                "reproducibility_summary": {
                                    "schema": "wenjin.harness.reproducibility_summary.v1",
                                    "script_paths": ["/workspace/scripts/eval.py"],
                                    "dependency_names": ["pandas"],
                                },
                                "experiment_interpretation_summary": {
                                    "schema": "wenjin.harness.experiment_interpretation_summary.v1",
                                    "interpretation_count": 1,
                                    "method_summary_count": 1,
                                    "metric_names": ["accuracy"],
                                    "verified_result_count": 1,
                                    "limitation_count": 1,
                                    "artifact_paths": ["/workspace/reports/model-eval.md"],
                                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                                },
                                "member_execution_transcript": {
                                    "schema": "wenjin.harness.member_execution_transcript.v1",
                                    "tool_call_count": 2,
                                    "tool_names": ["sandbox.run_python", "sandbox.write_file"],
                                    "completed_tool_count": 2,
                                    "failed_tool_count": 0,
                                    "changed_paths": ["/workspace/main/paper.tex"],
                                    "sandbox_job_ids": ["job-1"],
                                    "sandbox_environment_ids": ["env-1"],
                                    "scratch_refs": ["/workspace/tmp/tasks/exec-1/research_scout"],
                                    "output_ref_read_count": 2,
                                    "output_refs_read": [
                                        "/workspace/tmp/tasks/.harness/outputs/exec-1/research_scout/stdout.txt",
                                        "/workspace/tmp/tasks/.harness/not-output/debug.txt",
                                    ],
                                    "generated_artifact_count": 1,
                                },
                            }
                        },
                    }
                ]
            }
        },
        allowed_tools=["sandbox.run_python", "sandbox.read_file"],
    )

    assert bundle["capability_goal"] == "produce_workspace_review_package"
    assert bundle["member_role"] == "实验工程师"
    assert bundle["allowed_tools"] == [
        "sandbox.run_python",
        "sandbox.read_file",
        "sandbox.read_output_ref",
    ]
    assert bundle["workspace_roots"] == [
        "/workspace/main",
        "/workspace/datasets",
        "/workspace/scripts",
        "/workspace/outputs",
        "/workspace/reports",
    ]
    assert bundle["sandbox"]["task_scratch_path"] == "/workspace/tmp/tasks/exec-1/research_scout.v1__1"
    assert bundle["sandbox"]["task_contract"] == {
        "schema": "wenjin.workspace_sandbox.task_contract.v1",
        "execution_id": "exec-1",
        "node_id": "research_scout.v1__1",
        "invocation_id": "",
        "scratch_path": "/workspace/tmp/tasks/exec-1/research_scout.v1__1",
        "read_output_ref_tool": "sandbox.read_output_ref",
        "writable_scratch_roots": ["/workspace/tmp/tasks/exec-1/research_scout.v1__1"],
        "reviewable_artifact_roots": ["/workspace/outputs", "/workspace/reports"],
        "manifest_paths": {
            "datasets": "/workspace/datasets/manifest.json",
            "artifacts": "/workspace/reports/artifacts.json",
        },
        "rules": [
            "Use scratch_path for temporary task-local files that should not become user-facing artifacts.",
            "Do not list, search, edit, register, or cite output_ref_root paths as user-facing artifacts.",
            "Inspect explicit output refs under output_ref_root only with sandbox.read_output_ref.",
            "Promote durable files to /workspace/outputs or /workspace/reports and register them with sandbox.register_artifact.",
        ],
    }
    assert bundle["task_scratch_path"] == "/workspace/tmp/tasks/exec-1/research_scout.v1__1"
    assert "node_modules" in bundle["search_ignored_names"]
    assert bundle["recent_file_change_summary"] == {
        "schema": "wenjin.harness.file_change_summary.v1",
        "changed_paths": ["/workspace/main/paper.tex"],
    }
    assert bundle["sandbox_execution_summary"] == {
        "schema": "wenjin.harness.sandbox_execution_summary.v1",
        "python_runs": 1,
        "sandbox_job_ids": ["job-1"],
        "execution_lifecycle_count": 1,
        "job_statuses": ["succeeded"],
        "exit_codes": [0],
        "output_refs": ["/workspace/tmp/tasks/.harness/outputs/exec-1/research_scout/stdout.txt"],
    }
    assert bundle["output_ref_recovery"] == {
        "schema": "wenjin.harness.output_ref_recovery.v1",
        "read_tool": "sandbox.read_output_ref",
        "guidance": (
            "Use sandbox.read_output_ref with output_ref and optional start_line/end_line "
            "before rerunning expensive sandbox work."
        ),
        "refs": [
            {
                "output_ref": "/workspace/tmp/tasks/.harness/outputs/exec-1/research_scout/stdout.txt",
                "source": "sandbox_execution_summary",
            }
        ],
    }
    assert bundle["reproducibility_summary"] == {
        "schema": "wenjin.harness.reproducibility_summary.v1",
        "script_paths": ["/workspace/scripts/eval.py"],
        "dependency_names": ["pandas"],
    }
    assert bundle["experiment_interpretation_summary"] == {
        "schema": "wenjin.harness.experiment_interpretation_summary.v1",
        "interpretation_count": 1,
        "method_summary_count": 1,
        "metric_names": ["accuracy"],
        "verified_result_count": 1,
        "limitation_count": 1,
        "artifact_paths": ["/workspace/reports/model-eval.md"],
        "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
    }
    assert bundle["member_execution_transcript"] == {
        "schema": "wenjin.harness.member_execution_transcript.v1",
        "tool_call_count": 2,
        "tool_names": ["sandbox.run_python", "sandbox.write_file"],
        "completed_tool_count": 2,
        "failed_tool_count": 0,
        "changed_paths": ["/workspace/main/paper.tex"],
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "scratch_refs": ["/workspace/tmp/tasks/exec-1/research_scout"],
        "output_ref_read_count": 1,
        "output_refs_read": [
            "/workspace/tmp/tasks/.harness/outputs/exec-1/research_scout/stdout.txt"
        ],
        "generated_artifact_count": 1,
    }
    assert bundle["recent_execution_evidence"][0]["harness"]["member_execution_transcript"]["tool_call_count"] == 2
    assert bundle["harness_replan_signals"] == [
        {
            "schema": "wenjin.harness.replan_signal.v1",
            "trigger": "recoverable_python_failure",
            "failure_codes": ["python_exit_nonzero"],
            "recommended_action": "revise_code_same_member",
        }
    ]
    assert bundle["upstream_artifact_candidates"] == [
        {
            "path": "/workspace/reports/model-eval.md",
            "kind": "sandbox_report",
            "title": "Model evaluation",
        }
    ]


def test_context_member_execution_transcript_drops_raw_tool_payload() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "continue experiment"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-1",
                        "node_metadata": {
                            "harness": {
                                "member_execution_transcript": {
                                    "schema": "wenjin.harness.member_execution_transcript.v1",
                                    "tool_call_count": 2,
                                    "tool_names": ["sandbox.run_python", "sandbox.read_output_ref"],
                                    "completed_tool_count": 2,
                                    "failed_tool_count": 0,
                                    "failed_tools": [],
                                    "changed_paths": ["/workspace/reports/analysis.md"],
                                    "sandbox_job_ids": ["job-1"],
                                    "sandbox_environment_ids": ["env-1"],
                                    "scratch_refs": ["/workspace/tmp/tasks/exec-1/analysis_probe"],
                                    "generated_artifact_count": 1,
                                    "usage": {
                                        "input_tokens": 100,
                                        "output_tokens": 20,
                                        "total_tokens": 120,
                                        "prompt": "raw prompt should not enter context",
                                    },
                                    "billing": {
                                        "credits_charged": 1,
                                        "provider_payload": "raw billing payload",
                                    },
                                    "duration_ms": 250,
                                    "output_ref_read_count": 1,
                                    "output_refs_read": [
                                        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt"
                                    ],
                                    "raw_args": {"script": "print('raw script')"},
                                    "stdout": "raw stdout should not enter context",
                                    "stderr": "raw stderr should not enter context",
                                    "script": "print('raw script')",
                                }
                            }
                        },
                    }
                ]
            }
        },
    )

    assert bundle["member_execution_transcript"] == {
        "schema": "wenjin.harness.member_execution_transcript.v1",
        "tool_call_count": 2,
        "tool_names": ["sandbox.run_python", "sandbox.read_output_ref"],
        "completed_tool_count": 2,
        "failed_tool_count": 0,
        "changed_paths": ["/workspace/reports/analysis.md"],
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "scratch_refs": ["/workspace/tmp/tasks/exec-1/analysis_probe"],
        "generated_artifact_count": 1,
        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        "billing": {"credits_charged": 1},
        "duration_ms": 250,
        "output_ref_read_count": 1,
        "output_refs_read": ["/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt"],
    }
    rendered = render_harness_context_for_prompt(bundle)
    assert "raw prompt should not enter context" not in rendered
    assert "raw billing payload" not in rendered
    assert "raw stdout should not enter context" not in rendered
    assert "raw stderr should not enter context" not in rendered
    assert "print('raw script')" not in rendered


def test_context_includes_scratch_reference_without_promoting_it_to_artifact() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={
            "execution_id": "exec-2",
            "node_id": "writer",
            "inputs": {
                "upstream_context": {
                    "sandbox_outputs": [
                        {
                            "task_scratch_path": "/workspace/tmp/tasks/exec-1/analysis_probe",
                            "artifacts": [
                                {"path": "/workspace/artifacts/result.csv", "kind": "dataset"},
                                {"path": "/workspace/reports/result.md", "kind": "report"},
                            ],
                        },
                        {
                            "task_scratch_path": "/workspace/tmp/tasks/.harness/outputs/exec/node",
                            "artifacts": [
                                {"path": "/workspace/tmp/tasks/.harness/outputs/exec/node/stdout.txt"}
                            ],
                        },
                    ]
                }
            },
        },
        workspace_data={
            "upstream_sandbox_outputs": [
                {
                    "task_scratch_path": "/workspace/tmp/tasks/exec-1/analysis_probe",
                    "generated_artifacts": [{"path": "/workspace/outputs/figure.png", "kind": "figure"}],
                },
                {
                    "task_scratch_path": "/workspace/.wenjin/cache/secret",
                    "generated_artifacts": [{"path": "/workspace/.wenjin/cache/secret.txt"}],
                },
            ]
        },
        allowed_tools=["sandbox.read_file", "sandbox.run_python"],
    )

    assert bundle["scratch_refs"] == [
        {
            "path": "/workspace/tmp/tasks/exec-1/analysis_probe",
            "source": "upstream_sandbox_output",
        }
    ]
    assert bundle["upstream_artifact_candidates"] == [
        {"path": "/workspace/reports/result.md", "kind": "report"},
        {"path": "/workspace/outputs/figure.png", "kind": "figure"},
    ]
    text = json.dumps(bundle, ensure_ascii=False)
    assert "/workspace/artifacts/result.csv" not in text
    assert "/workspace/tmp/tasks/.harness/outputs" not in text
    assert "/workspace/.wenjin" not in text


def test_context_preserves_only_explicit_output_refs_in_sandbox_summary() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "continue experiment"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-1",
                        "node_metadata": {
                            "harness": {
                                "sandbox_execution_summary": {
                                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                                    "python_runs": 1,
                                    "output_refs": [
                                        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt",
                                        "/workspace/tmp/tasks/.harness/debug/private.json",
                                        "/workspace/.env",
                                        "/workspace/main/not-output.txt",
                                    ],
                                }
                            }
                        },
                    }
                ]
            }
        },
    )

    assert bundle["sandbox_execution_summary"]["output_refs"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt"
    ]


def test_context_sandbox_execution_summary_drops_raw_runtime_payload() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "continue experiment"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-1",
                        "node_metadata": {
                            "harness": {
                                "sandbox_execution_summary": {
                                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                                    "python_runs": 1,
                                    "failed_python_runs": 0,
                                    "recoverable_failures": 0,
                                    "sandbox_job_ids": ["job-1"],
                                    "sandbox_environment_ids": ["env-1"],
                                    "generated_artifact_count": 1,
                                    "execution_lifecycle_count": 1,
                                    "job_statuses": ["succeeded"],
                                    "exit_codes": [0],
                                    "output_refs": [
                                        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt"
                                    ],
                                    "stdout": "raw stdout should stay behind output refs",
                                    "stderr": "raw stderr should stay behind output refs",
                                    "traceback": "Traceback raw payload should not enter prompt context",
                                    "command": "python /workspace/scripts/private.py",
                                    "raw_payload": {"stdout": "nested raw output"},
                                }
                            }
                        },
                    }
                ]
            }
        },
    )

    assert bundle["sandbox_execution_summary"] == {
        "schema": "wenjin.harness.sandbox_execution_summary.v1",
        "python_runs": 1,
        "failed_python_runs": 0,
        "recoverable_failures": 0,
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "generated_artifact_count": 1,
        "execution_lifecycle_count": 1,
        "job_statuses": ["succeeded"],
        "exit_codes": [0],
        "output_refs": ["/workspace/tmp/tasks/.harness/outputs/exec-1/node/stdout.txt"],
    }
    rendered = render_harness_context_for_prompt(bundle)
    assert "raw stdout should stay behind output refs" not in rendered
    assert "raw stderr should stay behind output refs" not in rendered
    assert "Traceback raw payload should not enter prompt context" not in rendered
    assert "nested raw output" not in rendered


def test_harness_context_bundle_includes_bounded_workspace_file_summary() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "continue experiment"},
        workspace_data={
            "workspace_file_summary": {
                "dataset_provenance": [
                    {
                        "path": "/workspace/datasets/raw/survey.csv",
                        "source_kind": "upload",
                        "source_id": "asset-1",
                        "title": "Survey responses",
                        "content_hash": "sha256:abc123",
                        "license": "CC-BY-4.0",
                    },
                    {"path": "/workspace/outputs/result.json", "source_kind": "generated"},
                    {"path": "/workspace/datasets/.env", "source_kind": "secret"},
                ],
                "recent_outputs": [
                    {"path": "/workspace/outputs/result.json", "kind": "sandbox_output"},
                    {"path": "/workspace/reports/lit-review.md", "kind": "sandbox_report"},
                    {"path": "/workspace/tmp/tasks/.harness/outputs/exec/node/stdout.txt", "kind": "debug"},
                ],
                "recent_scripts": [
                    {"path": "/workspace/scripts/analysis.py"},
                    {"path": "/workspace/.wenjin/env/bin/python"},
                ],
            }
        },
    )

    summary = bundle["workspace_file_summary"]
    assert summary["visible_roots"] == [
        "/workspace/main",
        "/workspace/datasets",
        "/workspace/scripts",
        "/workspace/outputs",
        "/workspace/reports",
    ]
    assert summary["recent_outputs"] == [
        {"path": "/workspace/outputs/result.json", "kind": "sandbox_output"},
        {"path": "/workspace/reports/lit-review.md", "kind": "sandbox_report"},
    ]
    assert summary["recent_scripts"] == [{"path": "/workspace/scripts/analysis.py"}]
    assert summary["dataset_provenance"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "source_kind": "upload",
            "source_id": "asset-1",
            "title": "Survey responses",
            "content_hash": "sha256:abc123",
            "license": "CC-BY-4.0",
        }
    ]
    assert summary["truncated"] is False
    text = json.dumps(summary, ensure_ascii=False)
    assert "/workspace/tmp/tasks/.harness/outputs" not in text
    assert "/workspace/.wenjin" not in text


def test_harness_context_visible_roots_come_from_workspace_contract(monkeypatch) -> None:
    def fake_workspace_contract(*, workspace_id: str | None = None, workspace_type: str | None = None):
        return {
            "virtual_root": "/workspace",
            "directories": {
                "main": {"path": "/workspace/main", "purpose": "primary_project", "review_surface": "workspace"},
                "datasets": {"path": "/workspace/datasets", "purpose": "datasets", "review_surface": "workspace"},
                "scripts": {"path": "/workspace/scripts", "purpose": "scripts", "review_surface": "workspace"},
                "reports": {"path": "/workspace/reports", "purpose": "reports", "review_surface": "artifact"},
            },
            "artifact_roots": {"reports": "/workspace/reports"},
            "datasets_manifest_path": "/workspace/datasets/manifest.json",
            "artifacts_manifest_path": "/workspace/reports/artifacts.json",
            "workspace_profile": {
                "schema": "wenjin.workspace_sandbox.type_profile.v1",
                "workspace_type": workspace_type or "",
                "label": "Test workspace",
            },
            "path_classes": {
                "workspace": ["/workspace/main"],
                "datasets": ["/workspace/datasets"],
                "scripts": ["/workspace/scripts"],
                "artifacts": ["/workspace/reports"],
                "guidance": [],
                "protected": [],
                "internal": [],
            },
            "protected_paths": [],
            "internal_paths": [],
            "search_ignored_names": [],
            "rules": [],
        }

    monkeypatch.setattr(context_assembly, "build_agent_workspace_contract", fake_workspace_contract)

    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        workspace_data={
            "workspace_file_summary": {
                "recent_outputs": [
                    {"path": "/workspace/outputs/result.csv", "kind": "sandbox_output"},
                    {"path": "/workspace/reports/report.md", "kind": "sandbox_report"},
                ],
                "recent_scripts": [{"path": "/workspace/scripts/analysis.py"}],
                "dataset_provenance": [{"path": "/workspace/datasets/raw.csv", "source_id": "dataset-1"}],
            }
        },
    )

    expected_roots = [
        "/workspace/main",
        "/workspace/datasets",
        "/workspace/scripts",
        "/workspace/reports",
    ]
    assert bundle["workspace_roots"] == expected_roots
    assert bundle["workspace_file_summary"]["visible_roots"] == expected_roots
    assert bundle["workspace_file_summary"]["recent_outputs"] == [
        {"path": "/workspace/reports/report.md", "kind": "sandbox_report"}
    ]


def test_harness_context_bundle_filters_protected_and_internal_workspace_paths() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "inspect prior outputs"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "exec-secret",
                        "display_name": "debug",
                        "summary": "Full output at /workspace/tmp/tasks/.harness/outputs/exec/node/tool.txt",
                        "node_metadata": {
                            "harness": {
                                "tool_failure_summary": {
                                    "failure_codes": ["tool_error"],
                                    "path": "/workspace/.wenjin/cache/token",
                                }
                            }
                        },
                    }
                ]
            }
        },
    )

    text = json.dumps(bundle["recent_execution_evidence"], ensure_ascii=False)
    assert "/workspace/tmp/tasks/.harness/outputs" not in text
    assert "/workspace/.wenjin" not in text
    assert bundle["recent_execution_evidence"] == [
        {
            "execution_id": "exec-secret",
            "display_name": "debug",
            "harness": {"tool_failure_summary": {"failure_codes": ["tool_error"]}},
        }
    ]


def test_harness_context_bundle_marks_budget_truncation() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "run experiment"},
        workspace_data={
            "workspace_history": {
                "recent_executions": [
                    {"execution_id": f"exec-{index}", "summary": "x" * 1000}
                    for index in range(10)
                ]
            }
        },
        max_chars=1200,
    )

    assert bundle["budget"]["max_chars"] == 1200
    assert bundle["budget"]["truncated"] is True
    assert len(json.dumps(bundle, ensure_ascii=False)) <= 1200
    assert bundle["task"] == {"goal": "run experiment"}


def test_render_harness_context_for_prompt_uses_bounded_json() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        workspace_type="sci",
        task={"goal": "run experiment"},
    )

    text = render_harness_context_for_prompt(bundle)

    assert "wenjin.harness.context_bundle.v1" in text
    assert "/workspace/scripts" in text
