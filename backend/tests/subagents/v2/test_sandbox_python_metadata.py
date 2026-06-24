from __future__ import annotations

from src.agents.lead_agent.v2.sandbox_artifact_discovery import DISCOVERY_SCHEMA
from src.agents.lead_agent.v2.sandbox_artifact_review import collect_sandbox_artifact_candidates
from src.subagents.v2.types.sandbox import _sandbox_python_tool_call


def test_sandbox_python_tool_call_carries_harness_metadata() -> None:
    output = {
        "status": "completed",
        "exit_code": 0,
        "docker_image": "python:3.13-slim",
        "script_hash": "sha256:abc",
        "output_refs": ["/workspace/tmp/tasks/.harness/outputs/exec/node/inv/sandbox.run_python-abc.txt"],
        "generated_artifacts": [{"path": "/workspace/outputs/result.json"}],
        "execution_manifest": {"schema": "wenjin.harness.run_python.execution_manifest.v1"},
        "reproducibility_manifest": {"schema": "wenjin.harness.run_python.reproducibility_manifest.v1"},
        "experiment_narrative": {"schema": "wenjin.harness.run_python.experiment_narrative.v1"},
    }
    billing = {"type": "sandbox_operation_billing", "credits_charged": 1}

    call = _sandbox_python_tool_call(operation="python_script", output=output, billing=billing)

    assert call["name"] == "sandbox.run_python"
    assert call["status"] == "completed"
    assert call["output_refs"] == output["output_refs"]
    assert call["metadata"]["execution_manifest"]["schema"] == "wenjin.harness.run_python.execution_manifest.v1"
    assert call["metadata"]["reproducibility_manifest"]["schema"] == (
        "wenjin.harness.run_python.reproducibility_manifest.v1"
    )
    assert call["metadata"]["generated_artifacts"] == output["generated_artifacts"]


def test_sandbox_python_tool_call_does_not_synthesize_recoverable_error() -> None:
    failure_classification = {
        "category": "execution_error",
        "recoverable": False,
    }
    output = {
        "status": "failed",
        "exit_code": 1,
        "docker_image": "python:3.13-slim",
        "script_hash": "sha256:def",
        "failure_classification": failure_classification,
    }
    billing = {"type": "sandbox_operation_billing", "credits_charged": 1}

    call = _sandbox_python_tool_call(operation="python_script", output=output, billing=billing)

    assert call["metadata"]["failure_classification"] == failure_classification
    assert "recoverable_error" not in call["metadata"]


def test_sandbox_python_tool_call_artifacts_are_collectable_for_review() -> None:
    artifact = {
        "schema": DISCOVERY_SCHEMA,
        "path": "/workspace/reports/analysis.md",
        "root": "reports",
        "artifact_kind": "sandbox_report",
        "mime_type": "text/markdown",
        "size": 42,
        "content_hash": "sha256:analysis",
        "review_surface": "sandbox_artifact",
        "materialization_status": "candidate",
        "title": "Legacy sandbox analysis",
    }
    original_artifact = dict(artifact)
    output = {
        "status": "completed",
        "exit_code": 0,
        "docker_image": "python:3.13-slim",
        "script_hash": "sha256:ghi",
        "generated_artifacts": [artifact],
        "execution_manifest": {
            "schema": "wenjin.harness.run_python.execution_manifest.v1",
            "sandbox_job_id": "job-legacy-python",
            "sandbox_environment_id": "env-legacy-python",
        },
    }
    billing = {"type": "sandbox_operation_billing", "credits_charged": 1}

    call = _sandbox_python_tool_call(operation="python_script", output=output, billing=billing)
    candidates = collect_sandbox_artifact_candidates(
        {"legacy_sandbox_python": {"tool_calls": [call]}}
    )

    assert artifact == original_artifact
    assert call["generated_artifacts"][0]["sandbox_job_id"] == "job-legacy-python"
    assert call["generated_artifacts"][0]["sandbox_environment_id"] == "env-legacy-python"
    assert call["metadata"]["generated_artifacts"] == call["generated_artifacts"]
    assert [candidate["path"] for candidate in candidates] == ["/workspace/reports/analysis.md"]
    assert candidates[0]["source_task_id"] == "legacy_sandbox_python"
    assert candidates[0]["sandbox_job_id"] == "job-legacy-python"
    assert candidates[0]["sandbox_environment_id"] == "env-legacy-python"
