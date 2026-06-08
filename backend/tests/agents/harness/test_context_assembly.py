from __future__ import annotations

import json

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
                                }
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
    assert "**/.env" in bundle["sandbox"]["protected_paths"]
    assert "/workspace/outputs/harness/**" in bundle["sandbox"]["internal_paths"]
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
            },
        }
    ]
    assert bundle["budget"] == {"max_chars": 12000, "truncated": False}


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
                    {"path": "/workspace/outputs/harness/exec/node/stdout.txt", "kind": "debug"},
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
    assert "/workspace/outputs/harness" not in text
    assert "/workspace/.wenjin" not in text


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
                        "summary": "Full output at /workspace/outputs/harness/exec/node/tool.txt",
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
    assert "/workspace/outputs/harness" not in text
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
