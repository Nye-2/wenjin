from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.dataservice_client.contracts.mission import MissionItemDraftPayload
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.adapters import (
    MissionLeaseFenceAdapter,
    _append_under_current_lease,
    _parse_subagent_action,
    _selected_ref_context_reads,
    _subagent_action_tools,
    _tool_semantic_references,
)
from src.mission_runtime.reference_authority import (
    canonical_reference_read,
    canonical_reference_read_for_receipt,
)
from src.subagent_runtime.contracts import SubagentJobSpec, SubagentToolResult
from src.tools.orchestrator import (
    ResearchToolOutcome,
    ToolOutcomeStatus,
    ToolReference,
    VerificationStatus,
)


def test_subagent_provider_action_decodes_open_objects() -> None:
    action = _parse_subagent_action(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subagent_use_tool",
                    "args": {
                        "summary": "Search the pinned source",
                        "tool_name": "research.search",
                        "arguments_json": '{"query":"federated LoRA"}',
                        "partial_result_json": "{}",
                    },
                    "id": "worker-frame-1",
                }
            ],
        )
    )

    assert action.arguments == {"query": "federated LoRA"}
    assert action.result_json == {}


def test_subagent_provider_schema_has_no_open_objects_or_defaults() -> None:
    tools = _subagent_action_tools(
        {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        }
    )

    def assert_strict(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            assert "default" not in node
            assert "uniqueItems" not in node
            for value in node.values():
                assert_strict(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict(value)

    for tool in tools:
        assert_strict(tool["function"]["parameters"])


def test_subagent_complete_schema_binds_exact_typed_receipt_refs() -> None:
    tools = _subagent_action_tools(
        {
            "type": "object",
            "required": ["summary", "evidence_refs", "artifact_refs"],
            "properties": {
                "summary": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "artifact_refs": {"type": "array", "items": {"type": "string"}},
            },
        },
        tool_results=(
            SubagentToolResult(
                status="completed",
                summary="loaded",
                evidence_refs=("artifact-candidate:" + "a" * 64,),
            ),
        ),
    )

    complete = next(
        tool for tool in tools if tool["function"]["name"] == "subagent_complete"
    )
    result_schema = complete["function"]["parameters"]["properties"]["result_json"]
    assert result_schema["properties"]["evidence_refs"]["items"]["enum"] == [
        "artifact-candidate:" + "a" * 64
    ]
    assert result_schema["properties"]["artifact_refs"]["maxItems"] == 0


def test_subagent_complete_decodes_native_structured_result() -> None:
    action = _parse_subagent_action(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subagent_complete",
                    "args": {
                        "summary": "Review complete",
                        "result_json": {
                            "summary": "All checks passed",
                            "verdict": "pass",
                        },
                    },
                    "id": "worker-frame-2",
                }
            ],
        )
    )

    assert action.kind == "complete"
    assert action.result_json == {"summary": "All checks passed", "verdict": "pass"}


def test_semantic_reference_projection_omits_inline_tool_payloads() -> None:
    content = "科研计算结果" * 12_000
    outcome = ResearchToolOutcome(
        operation_id="operation-1",
        operation_key="a" * 64,
        producer="worker-1",
        tool_id="sandbox.read_artifact",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="Read verified artifact.",
        evidence_refs=(
            ToolReference(
                ref_id=f"sandbox-artifact:{'b' * 64}",
                kind="sandbox_artifact_manifest",
                metadata={
                    "path": "/workspace/outputs/result.json",
                    "content_hash": f"sha256:{'b' * 64}",
                    "kind": "application/json",
                    "content": content,
                    "verified_inline": True,
                },
            ),
        ),
        verification_status=VerificationStatus.VERIFIED,
    )

    [reference] = _tool_semantic_references(outcome)

    assert reference.metadata == {
        "path": "/workspace/outputs/result.json",
        "content_hash": f"sha256:{'b' * 64}",
        "kind": "application/json",
    }
    assert reference.source_type == "artifact"


def test_artifact_candidate_evidence_keeps_artifact_provenance() -> None:
    outcome = ResearchToolOutcome(
        operation_id="operation-artifact",
        operation_key="c" * 64,
        producer="worker-1",
        tool_id="artifact.create_candidate",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="Prepared a stage artifact.",
        evidence_refs=(
            ToolReference(
                ref_id=f"artifact-candidate:{'d' * 64}",
                kind="artifact_candidate",
                title="第一问建模边界",
            ),
        ),
        verification_status=VerificationStatus.VERIFIED,
    )

    [reference] = _tool_semantic_references(outcome)

    assert reference.source_type == "artifact"


def test_selected_refs_project_to_exact_canonical_read_arguments() -> None:
    common = {
        "job_id": "sj-projection",
        "operation_id": "op-projection",
        "mission_id": "mission-1",
        "workspace_id": "workspace-1",
        "model_id": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "lease_owner": "worker-1",
        "lease_epoch": 1,
        "display_name": "输入核验员",
        "role_label": "input_auditor",
        "task_summary": "Audit selected inputs",
        "objective": "Validate the current stage",
    }
    document_job = SubagentJobSpec(
        **common,
        selected_refs=("prism-file:file-123",),
        allowed_tools=("workspace.read_document",),
        tool_input_schemas={"workspace.read_document": {}},
    )
    candidate_job = SubagentJobSpec(
        **{**common, "job_id": "sj-candidate"},
        selected_refs=("artifact-candidate:" + "b" * 64,),
        allowed_tools=("artifact.read_candidate",),
        tool_input_schemas={"artifact.read_candidate": {}},
    )
    visual_job = SubagentJobSpec(
        **{**common, "job_id": "sj-visual"},
        selected_refs=("academic-visual:avc_result_1",),
        allowed_tools=("artifact.read_candidate",),
        tool_input_schemas={"artifact.read_candidate": {}},
    )
    artifact_job = SubagentJobSpec(
        **{**common, "job_id": "sj-artifact"},
        selected_refs=("sandbox-artifact:" + "a" * 64,),
        allowed_tools=("sandbox.read_artifact",),
        tool_input_schemas={"sandbox.read_artifact": {}},
    )

    assert [
        item.model_dump(mode="json")
        for item in _selected_ref_context_reads(
            document_job.selected_refs,
            document_job.allowed_tools,
        )
    ] == [
        {
            "ref": "prism-file:file-123",
            "tool_name": "workspace.read_document",
            "arguments": {"document_ref": "prism-file:file-123"},
        }
    ]
    assert [
        item.model_dump(mode="json")
        for item in _selected_ref_context_reads(
            visual_job.selected_refs,
            visual_job.allowed_tools,
        )
    ] == [
        {
            "ref": "academic-visual:avc_result_1",
            "tool_name": "artifact.read_candidate",
            "arguments": {"candidate_ref": "academic-visual:avc_result_1"},
        }
    ]
    assert [
        item.model_dump(mode="json")
        for item in _selected_ref_context_reads(
            candidate_job.selected_refs,
            candidate_job.allowed_tools,
        )
    ] == [
        {
            "ref": "artifact-candidate:" + "b" * 64,
            "tool_name": "artifact.read_candidate",
            "arguments": {"candidate_ref": "artifact-candidate:" + "b" * 64},
        }
    ]
    assert [
        item.model_dump(mode="json")
        for item in _selected_ref_context_reads(
            artifact_job.selected_refs,
            artifact_job.allowed_tools,
        )
    ] == [
        {
            "ref": "sandbox-artifact:" + "a" * 64,
            "tool_name": "sandbox.read_artifact",
            "arguments": {"artifact_ref": "sandbox-artifact:" + "a" * 64},
        }
    ]
    with pytest.raises(ValueError, match="selected_refs are not readable"):
        _selected_ref_context_reads(
            ("artifact-candidate:" + "b" * 64,),
            ("workspace.read_document", "sandbox.read_artifact"),
        )

    with pytest.raises(ValueError, match="sandbox-artifact"):
        _selected_ref_context_reads(
            ("sandbox-artifact:" + "c" * 64,),
            ("workspace.read_document",),
        )


def test_canonical_reference_authority_rejects_malformed_refs() -> None:
    assert canonical_reference_read("academic-visual:avc_result_1") is not None
    assert canonical_reference_read("academic-visual:-invalid") is None
    assert canonical_reference_read("artifact-candidate:" + "a" * 63) is None
    assert canonical_reference_read("sandbox-file:/workspace/outputs/result.json") is None


def test_receipt_authority_only_hydrates_safe_sandbox_text() -> None:
    artifact_ref = "sandbox-artifact:" + "a" * 64

    assert canonical_reference_read_for_receipt(
        artifact_ref,
        kind="sandbox_artifact_manifest",
        metadata={"kind": "application/json", "size_bytes": 128},
    ) is not None
    assert canonical_reference_read_for_receipt(
        artifact_ref,
        kind="sandbox_artifact_manifest",
        metadata={"kind": "image/png", "size_bytes": 128},
    ) is None
    assert canonical_reference_read_for_receipt(
        artifact_ref,
        kind="sandbox_artifact_manifest",
        metadata={"kind": "text/plain", "size_bytes": 0},
    ) is None
    assert canonical_reference_read_for_receipt(
        "academic-visual:avc_result_1",
        kind="academic_visual_candidate",
        metadata={},
    ) is not None
    assert canonical_reference_read_for_receipt(
        "academic-visual:avc_result_1",
        kind="artifact_candidate",
        metadata={},
    ) is None


@pytest.mark.asyncio
async def test_lease_fence_retries_same_lease_state_version_conflict() -> None:
    class RacingStore:
        def __init__(self) -> None:
            self.version = 7
            self.heartbeats = 0

        async def get(self, _mission_id: str):
            return SimpleNamespace(
                mission_id="mission-1",
                lease_owner="worker-1",
                lease_epoch=3,
                state_version=self.version,
            )

        async def heartbeat_lease(self, _mission_id: str, command):
            self.heartbeats += 1
            if self.heartbeats == 1:
                self.version += 1
                raise DataServiceClientError("concurrent same-lease update", status_code=409)
            assert command.expected_state_version == self.version
            self.version += 1
            return SimpleNamespace(state_version=self.version)

    store = RacingStore()
    fence = MissionLeaseFenceAdapter(store)  # type: ignore[arg-type]

    await fence.assert_current(SimpleNamespace(mission_id="mission-1", lease_epoch=3))

    assert store.heartbeats == 2


@pytest.mark.asyncio
async def test_effect_ledger_tolerates_sustained_same_lease_contention() -> None:
    class RacingStore:
        def __init__(self) -> None:
            self.version = 11
            self.appends = 0

        async def get(self, _mission_id: str):
            return SimpleNamespace(
                mission_id="mission-1",
                lease_owner="worker-1",
                lease_epoch=4,
                state_version=self.version,
            )

        async def append_items(self, _mission_id: str, command):
            self.appends += 1
            if self.appends <= 8:
                self.version += 1
                raise DataServiceClientError("concurrent same-lease update", status_code=409)
            assert command.expected_state_version == self.version
            self.version += 1
            return SimpleNamespace(
                mission=SimpleNamespace(
                    mission_id="mission-1",
                    lease_owner="worker-1",
                    lease_epoch=4,
                    state_version=self.version,
                )
            )

    store = RacingStore()
    mission = await _append_under_current_lease(
        store,  # type: ignore[arg-type]
        mission_id="mission-1",
        lease_owner="worker-1",
        lease_epoch=4,
        items=[
            MissionItemDraftPayload(
                item_type="subagent_progress",
                phase="progress",
                producer="subagent-1",
                summary="Concurrent progress",
            )
        ],
    )

    assert store.appends == 9
    assert mission.state_version == 20
