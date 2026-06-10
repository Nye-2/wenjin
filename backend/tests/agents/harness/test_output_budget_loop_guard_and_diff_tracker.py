from __future__ import annotations

from src.agents.harness.diff_tracker import (
    build_file_change,
    build_file_change_summary_from_tool_calls,
    build_harness_node_metadata_from_tool_calls,
)
from src.agents.harness.loop_guard import HarnessLoopGuard
from src.agents.harness.output_budget import (
    bounded_externalized_preview_budget,
    cap_text,
    select_lines,
)


def test_output_budget_caps_text_and_selects_line_window() -> None:
    content = "line 1\nline 2\nline 3\n"

    assert select_lines(content, start_line=2, end_line=2) == "line 2\n"
    assert cap_text("abcdef", 3) == ("abc", True)
    assert cap_text("abc", 3) == ("abc", False)


def test_externalized_preview_budget_keeps_head_tail_within_content_limit() -> None:
    assert bounded_externalized_preview_budget(
        head_chars=60,
        tail_chars=40,
        max_content_chars=20,
    ) == (12, 8)
    assert bounded_externalized_preview_budget(
        head_chars=5,
        tail_chars=5,
        max_content_chars=20,
    ) == (5, 5)


def test_diff_tracker_records_hashes_and_unified_diff() -> None:
    change = build_file_change(
        path="/workspace/main.tex",
        before="old\n",
        after="new\n",
        operation="update",
    )

    assert change["path"] == "/workspace/main.tex"
    assert change["operation"] == "update"
    assert change["before_hash"] != change["after_hash"]
    assert "-old" in change["unified_diff"]
    assert "+new" in change["unified_diff"]


def test_file_change_summary_collapses_tool_changes_by_path() -> None:
    first = build_file_change(
        path="/workspace/main.tex",
        before="old\n",
        after="middle\n",
        operation="update",
    )
    second = build_file_change(
        path="/workspace/main.tex",
        before="middle\n",
        after="new\n",
        operation="update",
    )
    added = build_file_change(
        path="/workspace/reports/summary.md",
        before=None,
        after="# Summary\n",
        operation="add",
    )

    summary = build_file_change_summary_from_tool_calls(
        [
            {"name": "sandbox.write_file", "status": "completed", "file_changes": [first]},
            {"name": "sandbox.str_replace", "status": "completed", "file_changes": [second]},
            {"name": "sandbox.write_file", "status": "completed", "file_changes": [added]},
        ]
    )

    assert summary["schema"] == "wenjin.harness.file_change_summary.v1"
    assert summary["changed_count"] == 2
    assert summary["reverted_count"] == 0
    assert summary["paths"] == ["/workspace/main.tex", "/workspace/reports/summary.md"]
    [main_change, report_change] = summary["changes"]
    assert main_change["path"] == "/workspace/main.tex"
    assert main_change["operation"] == "update"
    assert main_change["change_count"] == 2
    assert main_change["before_hash"] == first["before_hash"]
    assert main_change["after_hash"] == second["after_hash"]
    assert len(main_change["diffs"]) == 2
    assert report_change["operation"] == "add"


def test_file_change_summary_does_not_treat_missing_hashes_as_reverted() -> None:
    summary = build_file_change_summary_from_tool_calls(
        [
            {
                "name": "external_sandbox.write_file",
                "status": "completed",
                "file_changes": [
                    {
                        "path": "/workspace/notes.md",
                        "operation": "update",
                        "unified_diff": "",
                    }
                ],
            }
        ]
    )

    assert summary["changed_count"] == 1
    assert summary["reverted_count"] == 0
    assert summary["changes"][0]["operation"] == "update"


def test_file_change_summary_preserves_externalized_diff_refs() -> None:
    summary = build_file_change_summary_from_tool_calls(
        [
            {
                "name": "sandbox.write_file",
                "status": "completed",
                "file_changes": [
                    {
                        "path": "/workspace/main/large.tex",
                        "operation": "update",
                        "before_hash": "sha256:old",
                        "after_hash": "sha256:new",
                        "unified_diff": "Total output lines: 100\n\n[preview]",
                        "diff_output_refs": [
                            "/workspace/tmp/tasks/.harness/outputs/exec/node/invocation/sandbox.write_file.diff-abc.diff"
                        ],
                        "diff_externalized": True,
                        "diff_truncated": True,
                    }
                ],
            }
        ]
    )

    diff = summary["changes"][0]["diffs"][0]
    assert diff["unified_diff"] == "Total output lines: 100\n\n[preview]"
    assert diff["diff_externalized"] is True
    assert diff["diff_truncated"] is True
    assert diff["diff_output_refs"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec/node/invocation/sandbox.write_file.diff-abc.diff"
    ]


def test_harness_node_metadata_includes_tool_failure_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.read_file",
                "status": "failed",
                "args": {"path": "/workspace/.env"},
                "error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                "metadata": {
                    "recoverable_error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                    "error_code": "tool_error",
                },
            },
            {
                "name": "sandbox.grep",
                "status": "completed",
                "metadata": {
                    "recoverable_error": "invalid_regex: unterminated character set",
                    "error_code": "invalid_regex",
                },
            },
        ]
    )

    summary = metadata["harness"]["tool_failure_summary"]
    assert summary["schema"] == "wenjin.harness.tool_failure_summary.v1"
    assert summary["total_failed_calls"] == 1
    assert summary["total_recoverable_errors"] == 2
    assert summary["failed_tools"] == ["sandbox.read_file"]
    assert summary["recoverable_error_codes"] == ["tool_error", "invalid_regex"]
    assert summary["failures"][0] == {
        "name": "sandbox.read_file",
        "status": "failed",
        "error": "HarnessPathError: protected path is not accessible: /workspace/.env",
        "error_code": "tool_error",
        "recoverable": True,
        "args": {"path": "/workspace/.env"},
    }


def test_harness_node_metadata_includes_sandbox_execution_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "sandbox_job_id": "job-1",
                    "sandbox_environment_id": "env-1",
                },
                "generated_artifacts": [
                    {"path": "/workspace/outputs/result.json"},
                    {"path": "/workspace/reports/analysis.md"},
                ],
            },
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "recoverable_error": "python_exit_nonzero: exit_code=2",
                "error_code": "python_exit_nonzero",
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "sandbox_job_id": "job-2",
                    "sandbox_environment_id": "env-1",
                },
                "failure_classification": {
                    "schema": "wenjin.harness.run_python.failure_classification.v1",
                    "category": "user_code",
                    "reason": "nonzero_exit",
                    "failure_code": "python_exit_nonzero",
                    "recoverable": True,
                },
            },
        ]
    )

    summary = metadata["harness"]["sandbox_execution_summary"]
    assert summary == {
        "schema": "wenjin.harness.sandbox_execution_summary.v1",
        "python_runs": 2,
        "failed_python_runs": 1,
        "recoverable_failures": 1,
        "sandbox_job_ids": ["job-1", "job-2"],
        "sandbox_environment_ids": ["env-1"],
        "failure_codes": ["python_exit_nonzero"],
        "generated_artifact_count": 2,
    }


def test_harness_node_metadata_includes_reproducibility_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "reproducibility_manifest": {
                    "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
                    "tool": "sandbox.run_python",
                    "workspace_id": "ws-1",
                    "execution_id": "exec-1",
                    "node_id": "node-1",
                    "invocation_id": "invocation-1",
                    "script": {
                        "name": "analysis.py",
                        "path": "/workspace/scripts/analysis.py",
                    },
                    "sandbox": {
                        "environment_id": "env-1",
                        "run_job_id": "job-1",
                        "install_job_ids": ["install-1"],
                        "network_profile": "none",
                        "timeout_seconds": 30,
                    },
                    "dependencies": {
                        "requested": ["pandas"],
                        "installed": ["pandas"],
                    },
                    "artifacts": [
                        {
                            "path": "/workspace/reports/analysis.md",
                            "name": "analysis.md",
                            "kind": "markdown",
                            "size_bytes": 128,
                        }
                    ],
                    "command_audit": {
                        "run_verdict": "pass",
                        "run_risk_level": "low",
                        "install_verdicts": ["pass"],
                        "install_risk_levels": ["low"],
                    },
                },
                "experiment_narrative": {
                    "schema": "wenjin.harness.run_python.experiment_narrative.v1",
                    "status": "completed",
                    "script_path": "/workspace/scripts/analysis.py",
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                    "artifact_paths": ["/workspace/reports/analysis.md"],
                    "dependency_names": ["pandas"],
                    "next_actions": [
                        "Review generated artifacts before using them as workspace deliverables."
                    ],
                },
            }
        ]
    )

    summary = metadata["harness"]["reproducibility_summary"]
    assert summary == {
        "schema": "wenjin.harness.reproducibility_summary.v1",
        "python_runs": 1,
        "manifest_count": 1,
        "script_paths": ["/workspace/scripts/analysis.py"],
        "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
        "artifact_paths": ["/workspace/reports/analysis.md"],
        "dependency_names": ["pandas"],
        "sandbox_environment_ids": ["env-1"],
        "sandbox_job_ids": ["job-1"],
        "install_job_ids": ["install-1"],
        "command_risk_levels": ["low"],
        "narrative_count": 1,
        "next_actions": [
            "Review generated artifacts before using them as workspace deliverables."
        ],
    }


def test_harness_node_metadata_includes_experiment_interpretation_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "experiment_interpretation": {
                    "schema": "wenjin.harness.experiment_interpretation.v1",
                    "method_summary": "Computed benchmark accuracy from the held-out panel split.",
                    "metric_definitions": [
                        {
                            "name": "accuracy",
                            "definition": "Correct predictions divided by evaluated samples.",
                        }
                    ],
                    "verified_results": [
                        {
                            "metric": "accuracy",
                            "value": 0.91,
                            "artifact_path": "/workspace/outputs/result.json",
                        }
                    ],
                    "limitations": [
                        "Single split only; robustness under non-IID clients is not verified."
                    ],
                    "artifact_refs": ["/workspace/outputs/result.json"],
                    "dataset_paths": ["/workspace/datasets/panel.csv"],
                },
            }
        ]
    )

    summary = metadata["harness"]["experiment_interpretation_summary"]
    assert summary == {
        "schema": "wenjin.harness.experiment_interpretation_summary.v1",
        "interpretation_count": 1,
        "method_summary_count": 1,
        "metric_names": ["accuracy"],
        "verified_result_count": 1,
        "limitation_count": 1,
        "artifact_paths": ["/workspace/outputs/result.json"],
        "dataset_paths": ["/workspace/datasets/panel.csv"],
        "method_summaries": ["Computed benchmark accuracy from the held-out panel split."],
        "limitations": [
            "Single split only; robustness under non-IID clients is not verified."
        ],
    }


def test_experiment_interpretation_summary_filters_unsafe_paths() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "experiment_interpretation": {
                    "method_summary": "Computed benchmark accuracy.",
                    "metric_definitions": [{"name": "accuracy"}],
                    "verified_results": [
                        {
                            "metric": "accuracy",
                            "value": 0.91,
                            "artifact_path": "/workspace/tmp/tasks/.harness/outputs/exec/node/stdout.txt",
                        },
                        {
                            "metric": "accuracy",
                            "value": 0.91,
                            "artifact_path": "/workspace/outputs/result.json",
                        },
                    ],
                    "limitations": ["Only one split was evaluated."],
                    "artifact_refs": [
                        "/workspace/.env",
                        "/workspace/reports/summary.md",
                    ],
                    "dataset_paths": [
                        "/workspace/datasets/panel.csv",
                        "/workspace/datasets/../.env",
                    ],
                },
            }
        ]
    )

    summary = metadata["harness"]["experiment_interpretation_summary"]
    assert summary["artifact_paths"] == [
        "/workspace/outputs/result.json",
        "/workspace/reports/summary.md",
    ]
    assert summary["dataset_paths"] == ["/workspace/datasets/panel.csv"]


def test_harness_node_metadata_includes_statistical_robustness_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "statistical_check": {
                    "schema": "wenjin.harness.statistical_check.v1",
                    "method": "difference-in-differences",
                    "sample_size": 1250,
                    "metric_names": ["accuracy", "f1"],
                    "robustness_checks": [
                        {"name": "seed_sensitivity", "status": "passed"},
                        {"name": "ablation_without_privacy_adapter", "status": "passed"},
                    ],
                    "limitations": ["single public benchmark"],
                    "artifact_paths": ["/workspace/outputs/robustness.json"],
                    "dataset_paths": ["/workspace/datasets/panel.csv"],
                },
            },
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "statistical_check": {},
            }
        ]
    )

    summary = metadata["harness"]["statistical_robustness_summary"]
    assert summary == {
        "schema": "wenjin.harness.statistical_robustness_summary.v1",
        "check_count": 1,
        "method_count": 1,
        "metric_names": ["accuracy", "f1"],
        "sample_size_count": 1,
        "sample_sizes": [1250],
        "robustness_check_count": 2,
        "passed_robustness_check_count": 2,
        "failed_robustness_check_count": 0,
        "critical_failed_robustness_check_count": 0,
        "limitation_count": 1,
        "artifact_paths": ["/workspace/outputs/robustness.json"],
        "dataset_paths": ["/workspace/datasets/panel.csv"],
        "method_summaries": ["difference-in-differences"],
        "limitations": ["single public benchmark"],
        "failed_robustness_checks": [],
    }


def test_statistical_robustness_summary_filters_unsafe_paths_and_counts_critical_failures() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "metadata": {
                    "statistical_check": {
                        "method_summary": "Evaluate robustness across random seeds.",
                        "n": 250,
                        "metrics": [{"name": "accuracy"}],
                        "robustness_checks": [
                            {
                                "name": "seed_sensitivity",
                                "status": "failed",
                                "severity": "critical",
                            }
                        ],
                        "limitations": [{"text": "Small sample."}],
                        "artifact_paths": [
                            "/workspace/tmp/tasks/.harness/outputs/exec/node/stdout.txt",
                            "/workspace/reports/robustness.md",
                        ],
                        "dataset_paths": [
                            "/workspace/datasets/panel.csv",
                            "/workspace/datasets/../.env",
                        ],
                    }
                },
            }
        ]
    )

    summary = metadata["harness"]["statistical_robustness_summary"]
    assert summary["sample_sizes"] == [250]
    assert summary["metric_names"] == ["accuracy"]
    assert summary["passed_robustness_check_count"] == 0
    assert summary["failed_robustness_check_count"] == 1
    assert summary["critical_failed_robustness_check_count"] == 1
    assert summary["failed_robustness_checks"] == ["seed_sensitivity"]
    assert summary["artifact_paths"] == ["/workspace/reports/robustness.md"]
    assert summary["dataset_paths"] == ["/workspace/datasets/panel.csv"]


def test_harness_node_metadata_includes_member_execution_transcript() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "duration_ms": 1250,
                "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
                "billing": {"credits_charged": 1},
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "sandbox_job_id": "job-1",
                    "sandbox_environment_id": "env-1",
                    "task_scratch_path": "/workspace/tmp/tasks/exec-1/analysis_probe",
                },
                "generated_artifacts": [
                    {"path": "/workspace/outputs/result.json"},
                    {"path": "/workspace/reports/analysis.md"},
                ],
            },
            {
                "name": "sandbox.write_file",
                "status": "completed",
                "duration_ms": 100,
                "file_changes": [
                    build_file_change(
                        path="/workspace/reports/analysis.md",
                        before=None,
                        after="# Analysis\n",
                        operation="add",
                    )
                ],
            },
            {
                "name": "sandbox.read_file",
                "status": "failed",
                "args": {"path": "/workspace/.env", "content": "must not leak"},
                "error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                "metadata": {"error_code": "tool_error"},
            },
        ]
    )

    transcript = metadata["harness"]["member_execution_transcript"]
    assert transcript == {
        "schema": "wenjin.harness.member_execution_transcript.v1",
        "tool_call_count": 3,
        "tool_names": ["sandbox.run_python", "sandbox.write_file", "sandbox.read_file"],
        "completed_tool_count": 2,
        "failed_tool_count": 1,
        "failed_tools": ["sandbox.read_file"],
        "changed_paths": ["/workspace/reports/analysis.md"],
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "scratch_refs": ["/workspace/tmp/tasks/exec-1/analysis_probe"],
        "generated_artifact_count": 2,
        "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
        "billing": {"credits_charged": 1},
        "duration_ms": 1350,
    }
    assert "/workspace/.env" not in str(transcript)
    assert "must not leak" not in str(transcript)


def test_loop_guard_warns_then_stops_repeated_identical_tool_calls() -> None:
    guard = HarnessLoopGuard(warn_threshold=3, hard_limit=5)
    args = {"path": "/workspace/main.tex"}

    assert guard.record("sandbox.read_file", args).allowed
    assert guard.record("sandbox.read_file", args).allowed

    warning = guard.record("sandbox.read_file", args)
    assert warning.allowed
    assert warning.should_warn

    assert guard.record("sandbox.read_file", args).allowed
    stopped = guard.record("sandbox.read_file", args)
    assert not stopped.allowed
    assert stopped.stop_reason == "tool_loop_hard_stop"
