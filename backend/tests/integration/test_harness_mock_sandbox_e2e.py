from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.harness.contracts import HarnessToolResult
from src.agents.harness.research_task_eval import evaluate_research_task_evidence
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.dataservice_client.contracts.catalog import AgentTemplatePayload, CapabilitySkillPayload
from src.subagents.v2.types.react import _resolve_tools


def _capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="sci_experiment_team",
        workspace_type="sci",
        display_name="科研实验团队",
        runtime={"mode": "team_kernel", "allowed_tools": ["sandbox.run_python"]},
        graph_template={
            "phases": [
                {
                    "name": "research",
                    "tasks": [
                        {
                            "name": "literature_data_curator",
                            "skill_id": "literature-data-curator",
                            "outputs": [
                                {
                                    "kind": "library_item",
                                    "iterate_on": "output.papers",
                                    "mapping": {
                                        "title": "{{item.title}}",
                                        "authors": "{{item.authors}}",
                                        "year": "{{item.year}}",
                                        "venue": "{{item.venue}}",
                                        "url": "{{item.url}}",
                                        "abstract": "{{item.abstract}}",
                                        "source": "{{item.source}}",
                                        "external_id": "{{item.external_id}}",
                                        "evidence_level": "{{item.evidence_level}}",
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "writing",
                    "tasks": [
                        {
                            "name": "manuscript_writer",
                            "skill_id": "manuscript-writer",
                            "outputs": [
                                {
                                    "kind": "prism_file_change",
                                    "mapping": {
                                        "logical_key": "project:main",
                                        "path": "main.tex",
                                        "reason": "e2e_review_package_revision",
                                        "pending_content": "{{output.text}}",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        definition_json={
            "mission": {"primary_surface": "sandbox"},
            "context_policy": {"room_reads": {"library": {"max_items": 3}}},
            "sandbox_policy": {
                "mode": "required",
                "allowed_operations": ["run_python"],
                "resource_limits": {"timeout_seconds": 60},
            },
            "quality_gates": ["harness_replan_signal"],
            "team_policy": {
                "core_templates": [
                    "literature_data_curator.v1",
                    "evidence_analyst.v1",
                    "manuscript_writer.v1",
                ],
                "optional_templates": [],
                "capability_tools": ["sandbox.run_python"],
                "capability_skills": [
                    "literature-data-curator",
                    "evidence-analyst",
                    "manuscript-writer",
                ],
                "quality_pipeline": ["harness_replan_signal"],
                "limits": {
                    "max_iterations": 1,
                    "max_parallel_invocations": 1,
                    "max_invocations_total": 3,
                },
            },
        },
    )


def _brief() -> TaskBrief:
    return TaskBrief(
        capability_id="sci_experiment_team",
        raw_message="验证一个 mock 实验并生成 result.json",
        workspace_id="ws-e2e",
        user_id="user-1",
        brief={
            "workspace_type": "sci",
            "topic": "federated LLM experiment",
        },
        manuscript_context={
            "latex_project_id": "latex-e2e",
            "main_file": "main.tex",
        },
    )


class _MockCatalogAndReviewClient:
    def __init__(self) -> None:
        self.registered_assets: list[object] = []
        self.registered_artifacts: list[object] = []
        self.staged_prism_commands: list[object] = []

    async def list_agent_templates(self, *, enabled_only: bool = True):
        return [
            AgentTemplatePayload(
                id="literature_data_curator.v1",
                display_role="文献与数据整理员",
                category="research",
                description="Summarize workspace sources and dataset provenance.",
                persona_prompt="You are Wenjin's literature and data curator.",
                default_skills=["literature-data-curator"],
                tool_affinity={
                    "preferred": [],
                    "can_request": [],
                },
                risk_profile={
                    "filesystem": "read_only",
                    "code_execution": "none",
                    "room_write": "staged_only",
                },
            ),
            AgentTemplatePayload(
                id="evidence_analyst.v1",
                display_role="实验分析工程师",
                category="evidence",
                description="Run reproducible sandbox analysis.",
                persona_prompt="You are Wenjin's evidence analyst.",
                default_skills=["evidence-analyst"],
                tool_affinity={
                    "preferred": ["sandbox.run_python"],
                    "can_request": [],
                },
                risk_profile={
                    "filesystem": "sandbox_only",
                    "code_execution": "required",
                    "room_write": "staged_only",
                },
            ),
            AgentTemplatePayload(
                id="manuscript_writer.v1",
                display_role="论文改稿员",
                category="writing",
                description="Stage manuscript revisions through Prism review.",
                persona_prompt="You are Wenjin's manuscript writer.",
                default_skills=["manuscript-writer"],
                tool_affinity={
                    "preferred": [],
                    "can_request": [],
                },
                risk_profile={
                    "filesystem": "read_only",
                    "code_execution": "none",
                    "room_write": "staged_only",
                },
            ),
        ]

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        return [
            CapabilitySkillPayload(
                id="literature-data-curator",
                display_name="Literature Data Curator",
                worker_type="research",
                subagent_type="react",
                prompt=(
                    "Summarize the topic, workspace sources, and dataset provenance. "
                    "Do not run sandbox tools."
                ),
                config={"output_kind": "json"},
                skill_json={
                    "schema_version": "capability_skill.v2",
                    "id": "literature-data-curator",
                    "io_contract": {
                        "output_schema": {
                            "type": "object",
                            "required": ["text", "quality_gates_checked"],
                            "properties": {
                                "text": {"type": "string"},
                                "quality_gates_checked": {"type": "array"},
                            },
                        }
                    },
                    "quality_gates": ["harness_replan_signal"],
                },
            ),
            CapabilitySkillPayload(
                id="evidence-analyst",
                display_name="Evidence Analyst",
                worker_type="evidence",
                subagent_type="react",
                prompt=(
                    "Run the sandbox analysis and return JSON. "
                    "Operating rules: use sandbox.run_python only."
                ),
                config={"output_kind": "json"},
                skill_json={
                    "schema_version": "capability_skill.v2",
                    "id": "evidence-analyst",
                    "sandbox_access": {"mode": "required", "profiles": ["analysis"]},
                    "io_contract": {
                        "output_schema": {
                            "type": "object",
                            "required": ["text", "quality_gates_checked"],
                            "properties": {
                                "text": {"type": "string"},
                                "quality_gates_checked": {"type": "array"},
                            },
                        }
                    },
                    "quality_gates": ["harness_replan_signal"],
                },
            ),
            CapabilitySkillPayload(
                id="manuscript-writer",
                display_name="Manuscript Writer",
                worker_type="writing",
                subagent_type="react",
                prompt=(
                    "Write a concise manuscript revision grounded in the verified "
                    "literature and sandbox experiment result. Do not commit directly."
                ),
                config={"output_kind": "json"},
                skill_json={
                    "schema_version": "capability_skill.v2",
                    "id": "manuscript-writer",
                    "io_contract": {
                        "output_schema": {
                            "type": "object",
                            "required": ["text", "quality_gates_checked"],
                            "properties": {
                                "text": {"type": "string"},
                                "quality_gates_checked": {"type": "array"},
                            },
                        }
                    },
                    "quality_gates": ["harness_replan_signal"],
                },
            ),
        ]

    async def upsert_pending_prism_file_change(self, command):
        self.staged_prism_commands.append(command)
        return SimpleNamespace(id="review-prism-1")

    async def register_asset(self, command):
        self.registered_assets.append(command)
        return SimpleNamespace(id="asset-1")

    async def register_sandbox_artifact(self, command):
        self.registered_artifacts.append(command)
        return SimpleNamespace(id="artifact-1", review_item_id="review-1")

    async def list_review_items(self, **kwargs):
        if kwargs.get("target_domain") == "prism":
            if not self.staged_prism_commands:
                return []
            command = self.staged_prism_commands[0]
            return [
                SimpleNamespace(
                    id="review-prism-1",
                    target_kind="prism_file_change",
                    target_ref_json={
                        "latex_project_id": command.latex_project_id,
                        "logical_key": command.logical_key,
                        "path": command.path,
                    },
                    status="pending",
                    title="Revise main.tex",
                    summary="E2E review package revision",
                    payload_json={
                        "logical_key": command.logical_key,
                        "path": command.path,
                        "reason": command.reason,
                        "pending_content": command.pending_content,
                        "pending_hash": command.pending_hash,
                        "source_execution_id": command.source_execution_id,
                        "source_task_id": command.source_task_id,
                    },
                    preview_json={
                        "path": command.path,
                        "pending_content": command.pending_content,
                        "pending_hash": command.pending_hash,
                    },
                    result_json=None,
                    created_at=None,
                    updated_at=None,
                    applied_at=None,
                )
            ]
        if kwargs.get("target_domain") != "sandbox":
            return []
        if not self.registered_artifacts:
            return []
        artifact_payload = self.registered_artifacts[0]
        metadata = artifact_payload.metadata_json
        reproducibility = artifact_payload.reproducibility_json
        return [
            SimpleNamespace(
                id="review-1",
                batch_id="batch-1",
                workspace_id="ws-e2e",
                source_item_id="artifact-1",
                item_kind="sandbox_artifact",
                target_domain="sandbox",
                target_kind="sandbox_artifact",
                target_ref_json={
                    "sandbox_artifact_id": "artifact-1",
                    "workspace_asset_id": "asset-1",
                },
                status="pending",
                title="Accept sandbox artifact: sandbox_output",
                summary="/workspace/outputs/result.json",
                payload_json={
                    "sandbox_artifact_id": "artifact-1",
                    "workspace_asset_id": "asset-1",
                    "artifact_kind": "sandbox_output",
                    "path": "/workspace/outputs/result.json",
                    "title": metadata.get("title"),
                    "description": metadata.get("description"),
                    "notes": metadata.get("notes"),
                    "reproducibility": dict(reproducibility),
                },
                preview_json={
                    "path": "/workspace/outputs/result.json",
                    "mime_type": "application/json",
                    "content_hash": "sha256:result",
                    "title": metadata.get("title"),
                    "description": metadata.get("description"),
                },
                provenance_json={
                    "source_kind": "sandbox_job",
                    "source_id": "job-e2e-1",
                    "execution_id": "exec-harness-e2e",
                    "source_task_id": reproducibility.get("source_task_id"),
                    "sandbox_environment_id": reproducibility.get("sandbox_environment_id"),
                    "source_script": reproducibility.get("source_script"),
                    "dataset_paths": reproducibility.get("dataset_paths"),
                },
                result_json=None,
                error_text=None,
                sort_order=0,
                applied_at=None,
                created_at=None,
                updated_at=None,
            )
        ]


class _ClientContext:
    def __init__(self, client: _MockCatalogAndReviewClient) -> None:
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_team_harness_mock_sandbox_flow_stages_reviewable_artifact(monkeypatch) -> None:
    client = _MockCatalogAndReviewClient()
    node_events: list[dict] = []
    harness_events: list[tuple[str, str, dict]] = []
    captured: dict[str, object] = {}

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    async def publish_event(execution_id: str, event_name: str, payload: dict):
        harness_events.append((execution_id, event_name, payload))

    async def load_workspace_data(self, workspace_id: str):
        return {
            "workspace_file_summary": {
                "dataset_provenance": [
                    {
                        "path": "/workspace/datasets/panel.csv",
                        "source_id": "library-source-1",
                        "content_hash": "sha256:panel",
                        "license": "research-use",
                    }
                ],
                "recent_scripts": [],
                "recent_outputs": [],
            },
            "workspace_history": {
                "recent_executions": [
                    {
                        "execution_id": "old-exec",
                        "summary": "old safe summary",
                        "node_metadata": {
                            "harness": {
                                "sandbox_execution_summary": {
                                    "schema": "wenjin.harness.sandbox_execution_summary.v1",
                                    "generated_artifact_count": 1,
                                    "sandbox_job_ids": ["old-job"],
                                },
                                "file_change_summary": {
                                    "changed_paths": ["/workspace/.env"],
                                },
                            }
                        },
                    }
                ]
            }
        }

    async def fake_react_loop(**kwargs):
        user_payload = json.loads(kwargs["user_message"])
        role = user_payload.get("team_role")
        captured.setdefault("roles", []).append(role)
        captured.setdefault("system_prompts", {})[role] = kwargs["system_prompt"]
        if role == "文献与数据整理员":
            curator_context = user_payload["_harness_context"]
            assert curator_context["schema"] == "wenjin.harness.context_bundle.v1"
            assert curator_context["allowed_tools"] == []
            assert curator_context["workspace_file_summary"]["dataset_provenance"][0]["path"] == (
                "/workspace/datasets/panel.csv"
            )
            return json.dumps(
                {
                    "text": "Dataset panel.csv supports the mock federated LLM experiment.",
                    "papers": [
                        {
                            "title": "Federated LLM Experiment Benchmark",
                            "authors": ["Smith", "Lee"],
                            "year": 2025,
                            "venue": "Mock SCI",
                            "url": "https://example.org/federated-llm-benchmark",
                            "abstract": "Verified benchmark context for federated LLM evaluation.",
                            "source": "semantic_scholar",
                            "external_id": "paper-verified-1",
                            "evidence_level": "external_verified",
                        }
                    ],
                    "quality_gates_checked": ["harness_replan_signal"],
                },
                ensure_ascii=False,
            )
        if role == "论文改稿员":
            writer_prompt = kwargs["system_prompt"]
            assert "If output_ref_recovery.refs is non-empty" in writer_prompt
            assert "Reuse scratch_refs" in writer_prompt
            assert "before recreating prior experiments" in writer_prompt
            assert "task_scratch_path" in writer_prompt
            assert "/workspace/outputs or /workspace/reports" in writer_prompt
            writer_context = user_payload["_harness_context"]
            assert writer_context["schema"] == "wenjin.harness.context_bundle.v1"
            assert writer_context["allowed_tools"] == []
            assert writer_context["scratch_refs"] == [
                {
                    "path": "/workspace/tmp/tasks/exec-harness-e2e/team.1.evidence_analyst_v1.1",
                    "source": "member_execution_transcript",
                }
            ]
            assert writer_context["reproducibility_summary"]["script_paths"] == [
                "/workspace/scripts/analysis.py"
            ]
            assert writer_context["reproducibility_summary"]["artifact_paths"] == [
                "/workspace/outputs/result.json"
            ]
            assert writer_context["sandbox_execution_summary"]["execution_lifecycle_count"] == 1
            assert writer_context["sandbox_execution_summary"]["job_statuses"] == ["succeeded"]
            assert writer_context["sandbox_execution_summary"]["exit_codes"] == [0]
            assert writer_context["sandbox_execution_summary"]["output_refs"] == [
                "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
                "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
            ]
            assert writer_context["output_ref_recovery"] == {
                "schema": "wenjin.harness.output_ref_recovery.v1",
                "read_tool": "sandbox.read_output_ref",
                "guidance": (
                    "Use sandbox.read_output_ref with output_ref and optional start_line/end_line "
                    "before rerunning expensive sandbox work."
                ),
                "refs": [
                    {
                        "output_ref": (
                            "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
                            "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
                        ),
                        "source": "sandbox_execution_summary",
                    }
                ],
            }
            assert writer_context["experiment_interpretation_summary"] == {
                "schema": "wenjin.harness.experiment_interpretation_summary.v1",
                "interpretation_count": 1,
                "method_summary_count": 1,
                "metric_names": ["accuracy"],
                "verified_result_count": 1,
                "limitation_count": 1,
                "artifact_paths": ["/workspace/outputs/result.json"],
                "dataset_paths": ["/workspace/datasets/panel.csv"],
                "method_summaries": [
                    "Computed benchmark accuracy from the held-out panel split."
                ],
                "limitations": [
                    "Single split only; robustness under non-IID clients is not verified."
                ],
            }
            return json.dumps(
                {
                    "text": (
                        "\\documentclass{article}\\begin{document}"
                        "\\section{Results}"
                        "The verified benchmark context and sandbox metric of 0.91 "
                        "support the revised federated LLM experiment summary."
                        "\\end{document}"
                    ),
                    "quality_gates_checked": ["harness_replan_signal"],
                },
                ensure_ascii=False,
            )

        harness_context = kwargs["harness_context"]
        context_bundle = user_payload["_harness_context"]
        captured["context_bundle"] = context_bundle
        analyst_prompt = kwargs["system_prompt"]
        assert "If output_ref_recovery.refs is non-empty" in analyst_prompt
        assert "sandbox.read_output_ref is available" in analyst_prompt
        assert "Reuse scratch_refs" in analyst_prompt
        assert "Do not list, search, write, or register internal" in analyst_prompt
        assert context_bundle["schema"] == "wenjin.harness.context_bundle.v1"
        assert context_bundle["sandbox"]["root"] == "/workspace"
        assert "/workspace/scripts" in context_bundle["sandbox"]["standard_dirs"]
        assert "/workspace/outputs" in context_bundle["sandbox"]["artifact_roots"]
        assert context_bundle["workspace_type"] == "sci"
        assert context_bundle["workspace_file_summary"]["dataset_provenance"] == [
            {
                "path": "/workspace/datasets/panel.csv",
                "source_id": "library-source-1",
                "content_hash": "sha256:panel",
                "license": "research-use",
            }
        ]
        assert ".env" not in json.dumps(context_bundle["recent_execution_evidence"])

        harness_context.workspace_data["_harness_sandbox"] = SimpleNamespace(
            read_file=AsyncMock(return_value='{"ok": true, "metric": 0.91}\n')
        )
        tools = _resolve_tools(["sandbox.run_python"], harness_context)
        assert [tool.name for tool in tools] == ["sandbox_run_python", "sandbox_read_output_ref"]
        tool = next(item for item in tools if item.name == "sandbox_run_python")
        result_text = await tool.ainvoke(
            {
                "script": (
                    "import json\n"
                    "from pathlib import Path\n"
                    "Path('/workspace/outputs/result.json').write_text("
                    "json.dumps({'metric': 0.91}))\n"
                    "print(json.dumps({'ok': True, 'metric': 0.91}))\n"
                ),
                "script_name": "analysis.py",
                "dependency_hints": [],
            }
        )
        captured["tool_payload"] = json.loads(result_text)
        read_tool = next(item for item in tools if item.name == "sandbox_read_output_ref")
        read_result_text = await read_tool.ainvoke(
            {
                "output_ref": captured["tool_payload"]["output_refs"][0],
                "start_line": 1,
                "end_line": 1,
            }
        )
        captured["read_output_ref_payload"] = json.loads(read_result_text)
        return json.dumps(
            {
                "text": "experiment complete",
                "quality_gates_checked": ["harness_replan_signal"],
            },
            ensure_ascii=False,
        )

    async def fake_run_python(self, **kwargs):
        assert kwargs["script_name"] == "analysis.py"
        assert "Path('/workspace/outputs/result.json')" in kwargs["script"]
        return HarnessToolResult(
            preview_text="Python execution completed: {'ok': True, 'metric': 0.91}",
            structured_payload={
                "status": "completed",
                "operation": "python_script",
                "script_name": "analysis.py",
                "script_path": "/workspace/scripts/analysis.py",
                "sandbox_job_id": "job-e2e-1",
                "sandbox_environment_id": "env-e2e-1",
                "parsed_stdout": {"ok": True, "metric": 0.91},
                "execution_lifecycle": {
                    "schema": "wenjin.sandbox.execution_lifecycle.v1",
                    "status": "succeeded",
                    "sandbox_job_id": "job-e2e-1",
                    "exit_code": 0,
                    "outputs": {
                        "stdout_externalized": True,
                        "stderr_externalized": False,
                        "output_refs": [
                            "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
                            "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt",
                            "/workspace/main/not-output.txt",
                        ],
                        "generated_artifact_count": 2,
                    },
                },
                "generated_artifacts": [
                        {
                            "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
                            "path": "/workspace/outputs/result.json",
                            "title": "Mock experiment result",
                            "description": "Result JSON generated by the mock federated LLM experiment.",
                            "root": "outputs",
                            "artifact_kind": "sandbox_output",
                            "mime_type": "application/json",
                            "size": 16,
                            "content_hash": "sha256:result",
                            "source_script": "/workspace/scripts/analysis.py",
                            "dataset_paths": ["/workspace/datasets/panel.csv"],
                            "notes": "Use this JSON for the review package metrics.",
                            "review_surface": "sandbox_artifact",
                            "materialization_status": "candidate",
                        },
                    {
                        "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
                        "path": "/workspace/tmp/tasks/.harness/outputs/exec/tool/raw.txt",
                        "root": "outputs",
                        "artifact_kind": "sandbox_output",
                        "mime_type": "text/plain",
                        "size": 9,
                        "content_hash": "sha256:internal",
                        "review_surface": "sandbox_artifact",
                        "materialization_status": "candidate",
                    },
                ],
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "tool": "sandbox.run_python",
                    "workspace_id": "ws-e2e",
                    "execution_id": "exec-harness-e2e",
                    "node_id": "team.1.evidence_analyst_v1.1",
                    "invocation_id": "team.1.evidence_analyst_v1.1",
                    "script_name": "analysis.py",
                    "script_path": "/workspace/scripts/analysis.py",
                    "task_scratch_path": "/workspace/tmp/tasks/exec-harness-e2e/team.1.evidence_analyst_v1.1",
                    "dependency_hints": [],
                    "sandbox_job_id": "job-e2e-1",
                    "sandbox_environment_id": "env-e2e-1",
                    "network_profile": "none",
                    "timeout_seconds": 30,
                },
                "reproducibility_manifest": {
                    "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
                    "script": {
                        "name": "analysis.py",
                        "path": "/workspace/scripts/analysis.py",
                    },
                    "sandbox": {
                        "environment_id": "env-e2e-1",
                        "run_job_id": "job-e2e-1",
                        "install_job_ids": [],
                    },
                    "dependencies": {
                        "requested": [],
                        "installed": [],
                    },
                    "artifacts": [
                        {
                            "path": "/workspace/outputs/result.json",
                            "artifact_kind": "sandbox_output",
                        }
                    ],
                    "command_audit": {
                        "run_risk_level": "low",
                        "install_risk_levels": [],
                    },
                    "datasets": [
                        {
                            "path": "/workspace/datasets/panel.csv",
                            "source_id": "library-source-1",
                        }
                    ],
                },
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
                "experiment_narrative": {
                    "schema": "wenjin.harness.run_python.experiment_narrative.v1",
                    "status": "completed",
                    "script_path": "/workspace/scripts/analysis.py",
                    "task_scratch_path": "/workspace/tmp/tasks/exec-harness-e2e/team.1.evidence_analyst_v1.1",
                    "dataset_paths": ["/workspace/datasets/panel.csv"],
                    "artifact_paths": ["/workspace/outputs/result.json"],
                    "dependency_names": [],
                    "command_risk": "low",
                    "next_actions": ["复核 result.json 指标"],
                },
            },
            output_refs=(
                "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
                "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt",
            ),
        )

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: _ClientContext(client),
    )
    monkeypatch.setattr(LeadAgentRuntime, "_load_workspace_data", load_workspace_data)
    monkeypatch.setattr("src.subagents.v2.types.react._run_react_loop", fake_react_loop)
    monkeypatch.setattr(
        "src.agents.harness.sandbox_execution_tools.SandboxExecutionTools.run_python",
        fake_run_python,
    )

    runtime = LeadAgentRuntime(
        resolver=AsyncMock(resolve=AsyncMock(return_value=_capability())),
        publish_event=publish_event,
        get_workspace_type=AsyncMock(return_value="sci"),
        record_node_event=record_node_event,
    )

    report: TaskReport = await runtime.run_session(
        execution_id="exec-harness-e2e",
        brief=_brief(),
    )

    assert report.status == "completed", report.model_dump(mode="json")
    assert captured["roles"] == ["文献与数据整理员", "实验分析工程师", "论文改稿员"]
    assert len(report.outputs) == 1
    assert report.outputs[0].kind == "library_item"
    assert report.outputs[0].data.evidence_level == "external_verified"
    assert client.registered_assets
    assert client.registered_artifacts
    assert client.staged_prism_commands
    sandbox_review_item = next(item for item in report.review_items if item["kind"] == "sandbox_artifact")
    prism_review_item = next(item for item in report.review_items if item["kind"] == "prism_file_change")
    assert sandbox_review_item == {
        "id": "review-1",
        "kind": "sandbox_artifact",
        "status": "pending",
        "title": "Accept sandbox artifact: sandbox_output",
        "summary": "/workspace/outputs/result.json",
        "source": {
            "type": "sandbox_job",
            "execution_id": "exec-harness-e2e",
            "job_id": "job-e2e-1",
        },
        "target": {
            "kind": "sandbox_artifact",
            "path": "/workspace/outputs/result.json",
            "artifact_kind": "sandbox_output",
            "asset_id": "asset-1",
            "sandbox_artifact_id": "artifact-1",
        },
        "preview": {
            "mode": "artifact",
            "path": "/workspace/outputs/result.json",
            "mime_type": "application/json",
            "content_hash": "sha256:result",
        },
        "reproducibility": {
            "source_task_id": "team.1.evidence_analyst_v1.1",
            "sandbox_environment_id": "env-e2e-1",
            "source_script": "/workspace/scripts/analysis.py",
            "dataset_paths": ["/workspace/datasets/panel.csv"],
            "content_hash": "sha256:result",
        },
        "actions": [
            {"action": "accept_sandbox_artifact", "label": "保存到产物库"},
            {"action": "reject_sandbox_artifact", "label": "忽略"},
        ],
        "created_at": None,
        "updated_at": None,
        "applied_at": None,
    }
    assert prism_review_item["id"] == "review-prism-1"
    assert prism_review_item["target"]["logical_key"] == "project:main"
    assert prism_review_item["target"]["file_path"] == "main.tex"
    assert prism_review_item["source"]["execution_id"] == "exec-harness-e2e"
    assert prism_review_item["source"]["task_id"] == "manuscript_writer"
    assert prism_review_item["preview"]["content_contract"] == {
        "path": "main.tex",
        "content_format": "latex_document",
        "latex_shape": "document",
        "balanced_braces": True,
    }
    assert client.registered_assets[0].storage_path == "/workspace/outputs/result.json"
    assert client.registered_assets[0].title == "Mock experiment result"
    assert client.registered_assets[0].metadata_json["source_script"] == "/workspace/scripts/analysis.py"
    assert client.registered_assets[0].metadata_json["dataset_paths"] == ["/workspace/datasets/panel.csv"]
    assert client.registered_artifacts[0].path == "/workspace/outputs/result.json"
    assert client.registered_artifacts[0].reproducibility_json["source_script"] == (
        "/workspace/scripts/analysis.py"
    )
    assert client.registered_artifacts[0].reproducibility_json["dataset_paths"] == [
        "/workspace/datasets/panel.csv"
    ]

    completed_nodes = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    assert completed_nodes
    assert {node["node_metadata"]["template_id"] for node in completed_nodes} == {
        "literature_data_curator.v1",
        "evidence_analyst.v1",
        "manuscript_writer.v1",
    }
    experiment_node = next(
        node
        for node in completed_nodes
        if node["node_metadata"]["template_id"] == "evidence_analyst.v1"
    )
    harness = experiment_node["node_metadata"]["harness"]
    assert harness["sandbox_execution_summary"]["schema"] == (
        "wenjin.harness.sandbox_execution_summary.v1"
    )
    assert harness["sandbox_execution_summary"]["python_runs"] == 1
    assert harness["sandbox_execution_summary"]["sandbox_job_ids"] == ["job-e2e-1"]
    assert harness["sandbox_execution_summary"]["sandbox_environment_ids"] == ["env-e2e-1"]
    assert harness["sandbox_execution_summary"]["generated_artifact_count"] == 1
    assert harness["sandbox_execution_summary"]["execution_lifecycle_count"] == 1
    assert harness["sandbox_execution_summary"]["job_statuses"] == ["succeeded"]
    assert harness["sandbox_execution_summary"]["exit_codes"] == [0]
    assert harness["sandbox_execution_summary"]["output_refs"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
        "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
    ]
    assert harness["reproducibility_summary"]["schema"] == "wenjin.harness.reproducibility_summary.v1"
    assert harness["reproducibility_summary"]["script_paths"] == ["/workspace/scripts/analysis.py"]
    assert harness["reproducibility_summary"]["dataset_paths"] == ["/workspace/datasets/panel.csv"]
    assert "/workspace/outputs/result.json" in harness["reproducibility_summary"]["artifact_paths"]
    assert harness["reproducibility_summary"]["next_actions"] == ["复核 result.json 指标"]
    assert harness["experiment_interpretation_summary"]["schema"] == (
        "wenjin.harness.experiment_interpretation_summary.v1"
    )
    assert harness["experiment_interpretation_summary"]["metric_names"] == ["accuracy"]
    assert harness["experiment_interpretation_summary"]["artifact_paths"] == [
        "/workspace/outputs/result.json"
    ]
    assert harness["experiment_interpretation_summary"]["dataset_paths"] == [
        "/workspace/datasets/panel.csv"
    ]
    assert harness["member_execution_transcript"]["schema"] == (
        "wenjin.harness.member_execution_transcript.v1"
    )
    assert harness["member_execution_transcript"]["tool_names"] == [
        "sandbox.run_python",
        "sandbox.read_output_ref",
    ]
    assert harness["member_execution_transcript"]["output_refs_read"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
        "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
    ]
    assert harness["member_execution_transcript"]["output_ref_read_count"] == 1
    assert harness["member_execution_transcript"]["scratch_refs"] == [
        "/workspace/tmp/tasks/exec-harness-e2e/team.1.evidence_analyst_v1.1"
    ]
    assert "/workspace/.env" not in json.dumps(experiment_node, default=str)
    assert any(event_name == "execution.harness.tool_call.completed" for _, event_name, _ in harness_events)

    evaluation = evaluate_research_task_evidence(
        report,
        node_events=node_events,
        required_surfaces=(
            "literature",
            "experiment",
            "writing",
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        ),
    )
    assert evaluation.status == "pass"
    assert evaluation.coverage == {
        "literature": "pass",
        "experiment": "pass",
        "writing": "pass",
        "workflow_trace": "pass",
        "experiment_interpretation": "pass",
        "output_ref_reuse": "pass",
    }
    assert evaluation.evidence["workflow_trace"]["scratch_refs"] == [
        "/workspace/tmp/tasks/exec-harness-e2e/team.1.evidence_analyst_v1.1"
    ]
    assert evaluation.evidence["workflow_trace"]["sandbox_job_ids"] == ["job-e2e-1"]
    assert evaluation.evidence["workflow_trace"]["output_refs_read"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
        "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
    ]
    assert evaluation.evidence["output_ref_reuse"]["reused_output_refs"] == [
        "/workspace/tmp/tasks/.harness/outputs/exec-harness-e2e/"
        "team.1.evidence_analyst_v1.1/sandbox.run_python.stdout.txt"
    ]
