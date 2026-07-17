from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.agents.harness.stage_acceptance import evaluate_stage_acceptance
from src.contracts.review_policy import ReviewMode
from src.contracts.stage_acceptance import StageAcceptanceContract
from src.dataservice_client.contracts.catalog import MissionPolicyPayload, WorkerSkillPayload
from src.dataservice_client.contracts.mission import MissionItemPayload
from src.mission_runtime.adapters import StageAcceptanceAdapter
from src.mission_runtime.contracts import StageQualityRequest
from src.mission_runtime.production import (
    CeleryMissionWakeupPublisher,
    MissionProductionConfigurationError,
    PinnedMissionStartContext,
    PinnedStageAssessmentBuilder,
    PinnedStageContractResolver,
    PinnedToolPolicyResolver,
    StrictReviewCandidateBuilder,
    _academic_visual_artifact_kind,
    _academic_visual_asset_provenance,
    _resolve_tool_groups,
    build_production_tool_catalog,
    require_mission_model_profile,
    require_native_search_capability,
)
from src.models.capability_profile import WebSearchAPI
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
)
from src.services.skill_loader import SkillLoader
from src.tools.mission.artifact_candidates import (
    artifact_candidate_content_hash,
    artifact_candidate_ref,
)
from src.tools.orchestrator import ToolCallerKind
from tests.models.capability_fixtures import verified_capability_assessment

from .conftest import FakeMissionStore, MutableClock, ScriptedAgent, start_request


@pytest.mark.asyncio
async def test_celery_wakeup_publisher_schedules_delayed_slice() -> None:
    with patch("src.task.celery_app.celery_app.send_task") as send_task:
        await CeleryMissionWakeupPublisher().publish(
            "mission-1",
            command_hint="retry",
            delay_seconds=5,
        )

    send_task.assert_called_once_with(
        "src.task.tasks.drive_mission",
        args=["mission-1"],
        kwargs={"command_hint": "retry"},
        queue="long_running",
        countdown=5,
    )


def _quality_contract() -> StageAcceptanceContract:
    return StageAcceptanceContract.model_validate(
        {
            "schema_version": "stage_acceptance_contract.v2",
            "contract_id": "test.scope",
            "version": 1,
            "mission_policy_id": "test-policy",
            "workspace_type": "sci",
            "stage_id": "scope",
            "stage_goal": "Produce a grounded scope.",
            "minimum_criteria": [{"criterion_id": "bounded", "description": "The scope is bounded."}],
            "required_artifacts": [{"kind": "research_brief"}],
            "allowed_actions_if_failed": ["revise_existing", "stop_execution"],
            "advance_condition": "The scope passes.",
            "stop_condition": "The scope cannot be repaired.",
        }
    )


def _candidate_item(mission, *, seq: int = 1) -> MissionItemPayload:
    preview_text = "# Research brief"
    metadata = {
        "artifact_kind": "research_brief",
        "content_hash": artifact_candidate_content_hash(preview_text),
        "mime_type": "text/markdown",
        "preview_text": preview_text,
        "source_refs": ["prism-file:source-1"],
        "materialized": False,
    }
    candidate_ref = artifact_candidate_ref(metadata)
    return MissionItemPayload(
        id=f"candidate-{seq}",
        mission_id=mission.mission_id,
        seq=seq,
        item_type="artifact",
        operation_id="candidate-op",
        phase="completed",
        stage_id="scope",
        producer="tool_orchestrator",
        payload_json={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "title": "Research brief",
            "metadata": metadata,
            "verified": True,
            "receipt_operation_key": "candidate-op-key",
        },
        created_at=mission.created_at,
    )


@pytest.mark.asyncio
async def test_stage_assessment_reconstructs_internal_candidate_from_receipt(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    candidate = _candidate_item(mission)
    candidate_ref = str(candidate.payload_json["reference_id"])
    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-1",
            stage_id="scope",
            candidate_refs=[candidate_ref],
            assessment_json={
                "criterion_assessments": [
                    {
                        "criterion_id": "bounded",
                        "status": "pass",
                        "supporting_refs": [candidate_ref],
                        "rationale": "The candidate states a bounded scope and explicit exclusions.",
                    }
                ]
            },
            reference_items=[candidate],
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert [item.artifact_id for item in assessment.artifacts] == [candidate_ref]
    assert assessment.artifacts[0].kind == "research_brief"
    assert assessment.artifacts[0].manifest_ref == candidate_ref
    assert [(item.evidence_id, item.surface) for item in assessment.evidence] == [
        (candidate_ref, "writing")
    ]
    assert assessment.evidence[0].metadata["authority"] == (
        "content_addressed_candidate"
    )


@pytest.mark.asyncio
async def test_stage_assessment_auto_attaches_candidate_content_evidence(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None

    source_ref = "prism-file:source-1"
    preview_text = (
        f"# Research brief\n\nC1 is grounded in {source_ref}.\n\n"
        "## AI 使用披露与责任\n\nD1: The author verified the result."
    )
    metadata = {
        "artifact_kind": "research_brief",
        "content_hash": artifact_candidate_content_hash(preview_text),
        "mime_type": "text/markdown",
        "preview_text": preview_text,
        "source_refs": [source_ref],
        "materialized": False,
    }
    candidate_ref = artifact_candidate_ref(metadata)
    candidate = _candidate_item(mission).model_copy(
        update={
            "payload_ref": candidate_ref,
            "payload_json": {
                "reference_id": candidate_ref,
                "kind": "artifact_candidate",
                "title": "Research brief",
                "metadata": metadata,
                "verified": True,
                "receipt_operation_key": "candidate-op-key",
            },
        }
    )
    contract = _quality_contract().model_copy(
        update={
            "required_evidence_surfaces": (
                "writing",
                "claim_evidence_alignment",
                "ai_use_disclosure",
            )
        }
    )
    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-content-evidence",
            stage_id="scope",
            candidate_refs=[candidate_ref],
            assessment_json={
                "criterion_assessments": [
                    {
                        "criterion_id": "bounded",
                        "status": "pass",
                        "supporting_refs": [candidate_ref],
                        "rationale": "The candidate states the scope, source binding, and disclosure explicitly.",
                    }
                ],
                "evidence": [],
            },
            reference_items=[candidate],
            deadline_monotonic=100,
        ),
        contract,
    )

    assert {item.surface for item in assessment.evidence} == {
        "writing",
        "claim_evidence_alignment",
        "ai_use_disclosure",
    }
    assert evaluate_stage_acceptance(contract, assessment).result == "pass"


@pytest.mark.asyncio
async def test_stage_assessment_rejects_unverified_supporting_refs(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    candidate = _candidate_item(mission)
    candidate_ref = str(candidate.payload_json["reference_id"])

    with pytest.raises(MissionProductionConfigurationError, match="refs without"):
        await PinnedStageAssessmentBuilder().build(
            StageQualityRequest(
                mission=mission,
                operation_id="quality-1",
                stage_id="scope",
                candidate_refs=[candidate_ref],
                assessment_json={
                    "criterion_assessments": [
                        {
                            "criterion_id": "bounded",
                            "status": "pass",
                            "supporting_refs": [candidate_ref, "artifact-candidate:" + "c" * 64],
                            "rationale": "The claimed support includes an unverified candidate reference.",
                        }
                    ]
                },
                reference_items=[candidate],
                deadline_monotonic=100,
            ),
            _quality_contract(),
        )


@pytest.mark.asyncio
async def test_subagent_critique_has_no_stage_acceptance_authority(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    candidate = _candidate_item(mission, seq=2)
    candidate_ref = str(candidate.payload_json["reference_id"])
    audit_item = MissionItemPayload(
        id="item-audit",
        mission_id=mission.mission_id,
        seq=1,
        item_type="subagent_completed",
        operation_id="audit-op",
        phase="completed",
        stage_id="scope",
        producer="subagent_runtime",
        payload_json={
            "jobs": [
                {
                    "status": "completed",
                    "role_label": "按需批判",
                    "evidence_refs": [candidate_ref],
                    "result_json": {
                        "findings": ["A possible limitation"],
                        "repair_actions": ["Clarify the boundary"],
                    },
                }
            ]
        },
        created_at=mission.created_at,
    )
    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-1",
            stage_id="scope",
            candidate_refs=[candidate_ref],
            assessment_json={
                "criterion_assessments": [
                        {
                            "criterion_id": "bounded",
                            "status": "pass",
                            "supporting_refs": [candidate_ref],
                            "rationale": "The candidate defines a concrete scope despite the optional critique.",
                        }
                ]
            },
            recent_items=[audit_item],
            reference_items=[candidate],
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert [item.artifact_id for item in assessment.artifacts] == [candidate_ref]
    assert "critiques" not in assessment.model_dump(mode="json")


@pytest.mark.asyncio
async def test_stage_assessment_accepts_verified_artifact_receipt_as_evidence(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    tool_item = MissionItemPayload(
        id="item-tool",
        mission_id=mission.mission_id,
        seq=1,
        item_type="artifact",
        operation_id="sandbox-op-key",
        phase="completed",
        stage_id="scope",
        producer="tool_orchestrator",
        payload_json={
            "reference_id": "sandbox-artifact:verified-1",
            "kind": "sandbox_artifact_manifest",
            "title": "result.json",
            "uri": None,
            "metadata": {},
            "verified": True,
            "receipt_operation_key": "sandbox-op-key",
        },
        created_at=mission.created_at,
    )

    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-1",
            stage_id="scope",
            assessment_json={
                "evidence": [
                    {
                        "evidence_id": "sandbox-artifact:verified-1",
                        "surface": "experiment_reproducibility",
                        "kind": "sandbox_artifact_manifest",
                    }
                ]
            },
            recent_items=[],
            reference_items=[tool_item],
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert assessment.evidence[0].status == "verified"
    assert assessment.evidence[0].surface == "experiment_reproducibility"


@pytest.mark.asyncio
async def test_stage_assessment_rejects_surface_not_authorized_by_receipt(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    tool_item = MissionItemPayload(
        id="item-tool",
        mission_id=mission.mission_id,
        seq=1,
        item_type="artifact",
        operation_id="sandbox-op-key",
        phase="completed",
        stage_id="scope",
        producer="tool_orchestrator",
        payload_json={
            "reference_id": "sandbox-artifact:verified-1",
            "kind": "sandbox_artifact_manifest",
            "title": "result.json",
            "metadata": {},
            "verified": True,
            "receipt_operation_key": "sandbox-op-key",
        },
        created_at=mission.created_at,
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="surface is not authorized",
    ):
        await PinnedStageAssessmentBuilder().build(
            StageQualityRequest(
                mission=mission,
                operation_id="quality-1",
                stage_id="scope",
                assessment_json={
                    "evidence": [
                        {
                            "evidence_id": "sandbox-artifact:verified-1",
                            "surface": "literature",
                        }
                    ]
                },
                reference_items=[tool_item],
                deadline_monotonic=100,
            ),
            _quality_contract(),
        )


class PolicyDataService:
    def __init__(self, records):
        self.records = records
        self.skills = {item.id: item for item in all_skill_records()}

    async def get_mission_policy(self, **kwargs):
        return next(
            (item for item in self.records if item.id == kwargs["policy_id"] and item.workspace_type == kwargs["workspace_type"]),
            None,
        )

    async def get_worker_skill(self, skill_id):
        return self.skills[skill_id]


class ProductionStartDataService(PolicyDataService):
    def __init__(self, records, missions) -> None:
        super().__init__(records)
        self.missions = missions

    async def get_credit_summary(self, _user_id):
        return SimpleNamespace(
            model_dump=lambda: {
                "credits": 100,
                "reserved_credits": 0,
                "spendable_credits": 100,
            }
        )


def _pinned_start_context(dataservice) -> PinnedMissionStartContext:
    catalog = build_production_tool_catalog(
        SimpleNamespace(
            dataservice=dataservice,
            lease_guard=object(),
            sandbox_receipts=object(),
        )
    )
    return PinnedMissionStartContext(
        dataservice,
        tool_catalog=catalog,
    )


def policy_record(policy_id: str) -> MissionPolicyPayload:
    item = next(value for value in MissionPolicyLoader().read_seed_items() if value["data"]["id"] == policy_id)
    data = item["data"]
    return MissionPolicyPayload(
        id=data["id"],
        workspace_type=data["workspace_type"],
        schema_version=data["schema_version"],
        enabled=True,
        policy_json=data,
        content_hash=data["content_hash"],
        source_path=item["source_path"],
    )


def policy_record_with_review_modes(
    policy_id: str,
    *allowed_modes: ReviewMode,
) -> MissionPolicyPayload:
    record = policy_record(policy_id)
    policy = record.to_contract()
    restricted = policy.model_copy(
        update={
            "review_policy": policy.review_policy.model_copy(
                update={
                    "default_mode": allowed_modes[0],
                    "allowed_modes": allowed_modes,
                }
            )
        }
    )
    catalog = restricted.to_catalog_data(
        resolved_stage_contracts=list(
            record.policy_json["resolved_stage_contracts"]
        )
    )
    return MissionPolicyPayload(
        id=restricted.id,
        workspace_type=restricted.workspace_type,
        schema_version=restricted.schema_version,
        enabled=restricted.enabled,
        policy_json=catalog,
        content_hash=str(catalog["content_hash"]),
        source_path=record.source_path,
    )


def all_skill_records() -> list[WorkerSkillPayload]:
    records: list[WorkerSkillPayload] = []
    for item in SkillLoader().read_seed_items():
        data = item["data"]
        records.append(
            WorkerSkillPayload(
                id=data["id"],
                schema_version=data["schema_version"],
                enabled=data["enabled"],
                skill_json=data,
                content_hash=data["content_hash"],
                source_path=item["source_path"],
            )
        )
    return records


def routing_context(policy_id: str) -> dict[str, str]:
    return {
        "model_capability_profile_hash": "a" * 64,
        "policy_content_hash": policy_record(policy_id).content_hash,
    }


def verified_runtime_model() -> RuntimeModelConfig:
    assessment = verified_capability_assessment("gpt-5.6-sol")
    return RuntimeModelConfig(
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        category="llm",
        provider="OpenAI",
        model="gpt-5.6-sol",
        api_key="sk-test",
        base_url="https://api.nainai.love/v1",
        generation_api=assessment.profile.generation_api,
        max_tokens=128000,
        temperature=0.2,
        timeout_seconds=60,
        max_retries=0,
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
        default_headers={},
        pricing_policy_id="model-standard",
        is_default=True,
        config_version=1,
    )


@pytest.mark.asyncio
async def test_start_context_pins_policy_stages_tools_and_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    monkeypatch.setattr(
        "src.mission_runtime.production.require_native_search_capability",
        lambda _model: SimpleNamespace(available=True),
    )
    resolver = _pinned_start_context(PolicyDataService([policy_record("sci_research")]))
    pinned = await resolver.pin(
        start_request(
            mission_policy_id="sci_research",
            runtime_context_json=routing_context("sci_research"),
            snapshot_json={"intake": {"target_outcome": "literature_positioning"}},
        )
    )

    runtime = pinned.runtime_context_json
    assert runtime["policy_ref"].startswith("sci_research@")
    assert runtime["required_stage_ids"] == [
        "scope_topic",
        "literature_positioning",
    ]
    assert "research.search_web" in runtime["tool_policy"]["allowed_tool_ids"]
    assert "academic_visual.render_candidate" in runtime["tool_policy"]["allowed_tool_ids"]
    assert "academic_visual_scoped" in runtime["tool_policy"]["allowed_network_profiles"]
    assert len(runtime["tool_policy"]["catalog_snapshot_hash"]) == 64
    execution_limits = {
        item["tool_id"]: item
        for item in runtime["tool_policy"]["execution_limits"]
    }
    assert set(execution_limits) == set(
        runtime["tool_policy"]["allowed_tool_ids"]
    )
    assert execution_limits["academic_visual.render_candidate"][
        "timeout_seconds"
    ] == 150
    assert execution_limits["academic_visual.render_candidate"][
        "max_attempts"
    ] == 1
    assert all(len(item["descriptor_hash"]) == 64 for item in execution_limits.values())
    resolved_tool_policy = await PinnedToolPolicyResolver().resolve(
        SimpleNamespace(runtime_context_json=runtime),
        caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        allowed_tools=("academic_visual.render_candidate",),
    )
    assert resolved_tool_policy.execution_limits[0].timeout_seconds == 150
    assert resolved_tool_policy.execution_limits[0].max_attempts == 1
    assert set(runtime["required_stage_ids"]).issubset(runtime["stage_contracts"])
    assert set(runtime["worker_skill_snapshots"]) == set(policy_record("sci_research").to_contract().allowed_worker_skills)
    for skill_id, snapshot in runtime["worker_skill_snapshots"].items():
        assert snapshot["contract"]["id"] == skill_id
        assert len(snapshot["content_hash"]) == 64
        assert set(snapshot["allowed_tool_ids"]).issubset(runtime["tool_policy"]["allowed_tool_ids"])


@pytest.mark.asyncio
async def test_start_context_rejects_review_mode_outside_pinned_policy(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    record = policy_record_with_review_modes(
        "sci_research",
        ReviewMode.BALANCED_DEFAULT,
    )
    resolver = _pinned_start_context(PolicyDataService([record]))

    with pytest.raises(
        MissionProductionConfigurationError,
        match="not allowed by the pinned MissionPolicy",
    ):
        await resolver.pin(
            start_request(
                mission_policy_id="sci_research",
                review_mode=ReviewMode.AUTO_DRAFT,
                runtime_context_json={
                    "model_capability_profile_hash": "a" * 64,
                    "policy_content_hash": record.content_hash,
                },
            )
        )


@pytest.mark.asyncio
async def test_pinned_resolver_resolves_math_per_question_stage(
    monkeypatch,
    runtime_factory,
) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    start_context = _pinned_start_context(PolicyDataService([policy_record("math_modeling_solution")]))
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([]),
        start_context=start_context,
    )
    receipt = await runtime.start(
        start_request(
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=routing_context("math_modeling_solution"),
            snapshot_json={
                "intake": {
                    "problem_statement": "Complete statement",
                    "problem_questions": ["q1", "q2"],
                }
            },
        )
    )
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None

    contract = await PinnedStageContractResolver().resolve(
        mission,
        "question_1_model",
    )

    assert contract.stage_id == "question_model"
    assert contract.instantiation.instance_id_template == "question_{index}_model"
    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-question-1",
            stage_id="question_1_model",
            deadline_monotonic=100,
        ),
        contract,
    )
    assert assessment.sequence_index == 1


@pytest.mark.asyncio
async def test_stage_adapter_resolves_all_item_count_from_referenced_stage_family(
    monkeypatch,
    runtime_factory,
) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    start_context = _pinned_start_context(PolicyDataService([policy_record("math_modeling_solution")]))
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([]),
        start_context=start_context,
    )
    receipt = await runtime.start(
        start_request(
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=routing_context("math_modeling_solution"),
        )
    )
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    mission.snapshot_json["stage_item_counts"] = {"problem_questions": 2}

    adapter = StageAcceptanceAdapter(
        contracts=PinnedStageContractResolver(),
        assessments=PinnedStageAssessmentBuilder(),
    )
    allowed, missing = await adapter.can_start(mission, "paper_integration")

    assert allowed is False
    assert missing == (
        "question_1_solution_validation",
        "question_2_solution_validation",
    )


@pytest.mark.asyncio
async def test_start_context_rejects_routing_policy_hash_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    resolver = _pinned_start_context(PolicyDataService([policy_record("sci_research")]))

    with pytest.raises(MissionProductionConfigurationError, match="changed after"):
        await resolver.pin(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json={
                    "model_capability_profile_hash": "a" * 64,
                    "policy_content_hash": "f" * 64,
                },
            )
        )


@pytest.mark.asyncio
async def test_start_context_rejects_worker_skill_hash_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    monkeypatch.setattr(
        "src.mission_runtime.production.require_native_search_capability",
        lambda _model: SimpleNamespace(available=True),
    )
    dataservice = PolicyDataService([policy_record("sci_research")])
    actual = dataservice.skills["research-scout"].to_contract()
    dataservice.skills["research-scout"] = SimpleNamespace(
        id="research-scout",
        enabled=True,
        content_hash="f" * 64,
        to_contract=lambda: actual,
    )

    with pytest.raises(MissionProductionConfigurationError, match="hash drift"):
        await _pinned_start_context(dataservice).pin(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json=routing_context("sci_research"),
            )
        )


@pytest.mark.asyncio
async def test_start_context_fails_closed_without_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    resolver = _pinned_start_context(PolicyDataService([]))
    with pytest.raises(MissionProductionConfigurationError, match="unavailable"):
        await resolver.pin(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json=routing_context("sci_research"),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "policy_id"),
    [
        ("math_modeling", "math_modeling_solution"),
        ("software_copyright", "software_copyright_application"),
    ],
)
async def test_non_search_policies_start_without_search_capability(
    monkeypatch,
    workspace_type: str,
    policy_id: str,
) -> None:
    model = SimpleNamespace(capability_probe_hash="a" * 64)
    search_requirement = Mock(side_effect=AssertionError("non-search policy must not require search"))
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: model,
    )
    monkeypatch.setattr(
        "src.mission_runtime.production.require_native_search_capability",
        search_requirement,
    )
    resolver = _pinned_start_context(PolicyDataService([policy_record(policy_id)]))

    pinned = await resolver.pin(
        start_request(
            workspace_type=workspace_type,
            mission_policy_id=policy_id,
            runtime_context_json=routing_context(policy_id),
        )
    )

    tool_policy = pinned.runtime_context_json["tool_policy"]
    assert tool_policy["allowed_tool_ids"]
    assert tool_policy["port_capabilities"] == ["review_candidate"]
    assert "workspace.list_assets" in tool_policy["allowed_tool_ids"]
    assert set(policy_record(policy_id).to_contract().tool_policy.allowed_tool_groups).issubset(tool_policy["granted_permissions"])
    expected_tool = "sandbox.run_python" if workspace_type == "math_modeling" else "source_code.read_file"
    assert expected_tool in tool_policy["allowed_tool_ids"]
    search_requirement.assert_not_called()


@pytest.mark.asyncio
async def test_search_policy_fails_at_start_when_search_probe_is_missing(
    monkeypatch,
) -> None:
    model = SimpleNamespace(capability_probe_hash="a" * 64)
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: model,
    )
    monkeypatch.setattr(
        "src.mission_runtime.production.require_native_search_capability",
        Mock(side_effect=MissionProductionConfigurationError("independent search transport is unavailable")),
    )
    resolver = _pinned_start_context(PolicyDataService([policy_record("sci_research")]))

    with pytest.raises(
        MissionProductionConfigurationError,
        match="independent search transport is unavailable",
    ):
        await resolver.pin(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json=routing_context("sci_research"),
            )
        )


@pytest.mark.asyncio
async def test_math_policy_starts_through_complete_production_builder() -> None:
    from src.mission_runtime.composition import build_production_mission_runtime

    reset_model_catalog_cache()
    model = verified_runtime_model()
    install_model_catalog_snapshot([model])
    store = FakeMissionStore(MutableClock())
    dataservice = ProductionStartDataService(
        [policy_record("math_modeling_solution")],
        store,
    )
    runtime = await build_production_mission_runtime(dataservice)  # type: ignore[arg-type]
    request = start_request(
        workspace_type="math_modeling",
        mission_policy_id="math_modeling_solution",
        runtime_context_json={
            "model_capability_profile_hash": model.capability_probe_hash,
            "policy_content_hash": policy_record("math_modeling_solution").content_hash,
        },
        snapshot_json={"intake": {"problem_statement": "A complete modeling problem statement"}},
    )

    with patch("src.task.celery_app.celery_app.send_task") as send_task:
        receipt = await runtime.start(request)

    created = await store.get(receipt.mission_id)
    assert receipt.created is True
    assert created is not None
    assert "sandbox.run_python" in created.runtime_context_json["tool_policy"]["allowed_tool_ids"]
    send_task.assert_called_once()
    reset_model_catalog_cache()


@pytest.mark.asyncio
async def test_sci_policy_starts_with_verified_release_search_probe() -> None:
    from src.mission_runtime.composition import build_production_mission_runtime

    reset_model_catalog_cache()
    model = verified_runtime_model()
    install_model_catalog_snapshot([model])
    store = FakeMissionStore(MutableClock())
    dataservice = ProductionStartDataService(
        [policy_record("sci_research")],
        store,
    )
    runtime = await build_production_mission_runtime(dataservice)  # type: ignore[arg-type]

    with patch("src.task.celery_app.celery_app.send_task") as send_task:
        receipt = await runtime.start(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json={
                    "model_capability_profile_hash": model.capability_probe_hash,
                    "policy_content_hash": policy_record("sci_research").content_hash,
                },
            )
        )
    created = await store.get(receipt.mission_id)
    assert receipt.created is True
    assert created is not None
    assert "research.search_web" in created.runtime_context_json["tool_policy"][
        "allowed_tool_ids"
    ]
    send_task.assert_called_once()
    reset_model_catalog_cache()


def test_unknown_tool_group_is_rejected_instead_of_ignored() -> None:
    policy = policy_record("math_modeling_solution").to_contract()
    invalid_tool_policy = policy.tool_policy.model_copy(update={"allowed_tool_groups": ("unknown_runtime_surface",)})
    invalid_policy = policy.model_copy(update={"tool_policy": invalid_tool_policy})

    with pytest.raises(
        MissionProductionConfigurationError,
        match="unknown tool group",
    ):
        _resolve_tool_groups(invalid_policy)


@pytest.mark.parametrize(
    "policy_id",
    [
        "sci_research",
        "thesis_research",
        "proposal_development",
        "software_copyright_application",
        "math_modeling_solution",
        "patent_development",
    ],
)
def test_every_workspace_policy_resolves_to_real_registrations(policy_id: str) -> None:
    resolution = _resolve_tool_groups(policy_record(policy_id).to_contract())

    assert resolution.tool_ids
    assert "review_candidate" in resolution.port_capabilities


def test_base_model_profile_does_not_require_search(monkeypatch) -> None:
    evidence = SimpleNamespace(
        web_search_api=WebSearchAPI.RESPONSES_WEB_SEARCH,
        search_receipts=(),
        checks=(),
        check_passed=lambda _name: False,
    )
    model = SimpleNamespace(
        base_url="https://api.nainai.love/v1",
        capability_freshness=lambda: SimpleNamespace(current=True),
        capability_profile=SimpleNamespace(protocol_conformance=True),
        has_strict_tools=lambda: True,
        capability_probe=evidence,
    )
    monkeypatch.setattr(
        "src.mission_runtime.production.get_runtime_model_config",
        lambda _model_id: model,
    )
    assert require_mission_model_profile("gpt-5.6-sol") is model


def test_search_requirement_fails_closed_without_search_receipts() -> None:
    evidence = SimpleNamespace(
        web_search_api=WebSearchAPI.RESPONSES_WEB_SEARCH,
        search_receipts=(),
        checks=(),
        check_passed=lambda _name: False,
    )
    model = SimpleNamespace(
        base_url="https://api.nainai.love/v1",
        capability_freshness=lambda: SimpleNamespace(current=True),
        capability_probe=evidence,
    )
    with pytest.raises(
        MissionProductionConfigurationError,
        match="independent search transport is unavailable",
    ):
        require_native_search_capability(model)


@pytest.mark.asyncio
async def test_pinned_resolvers_never_silently_allow_missing_contracts() -> None:
    run = SimpleNamespace(
        runtime_context_json={},
        mission_policy_id="sci_research",
        workspace_type="sci",
    )
    with pytest.raises(MissionProductionConfigurationError, match="tool policy"):
        await PinnedToolPolicyResolver().resolve(
            run,
            caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        )
    with pytest.raises(MissionProductionConfigurationError, match="stage contract"):
        await PinnedStageContractResolver().resolve(run, "scope_topic")


@pytest.mark.asyncio
async def test_review_builder_requires_atomic_preview() -> None:
    request = SimpleNamespace(candidate_json={"items": []}, reference_items=[])
    with pytest.raises(MissionProductionConfigurationError, match="atomic preview"):
        await StrictReviewCandidateBuilder().build_candidates(request)


def _review_candidate_reference():
    body = "# 问题理解\n\n完整正文。"
    metadata = {
        "artifact_kind": "modeling_problem_brief",
        "content_hash": artifact_candidate_content_hash(body),
        "mime_type": "text/markdown",
        "preview_text": body,
        "source_refs": ["prism-file:problem-1"],
        "materialized": False,
    }
    ref = artifact_candidate_ref(metadata)
    return ref, SimpleNamespace(
        item_type="artifact",
        seq=7,
        payload_json={
            "reference_id": ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": metadata,
        },
    )


def _source_review_candidate_reference():
    url = "https://example.org/papers/federated-peft"
    verification_ref = "search-receipt:search-op#source-1"
    source_import_payload = {
        "source_kind": "paper",
        "title": "Federated PEFT",
        "authors_json": ["Ada Researcher"],
        "year": 2026,
        "venue": "Journal of Reliable Research",
        "doi": "10.1000/fedpeft",
        "url": url,
        "abstract": "A verified source candidate.",
        "ingest_kind": "mission_verified",
        "ingest_label": verification_ref,
        "library_status": "candidate",
        "evidence_level": "external_verified",
        "citation_key": "Researcher2026FedPEFT",
    }
    preview_text = "# Source import candidate\n\nverified"
    metadata = {
        "title": source_import_payload["title"],
        "artifact_kind": "source_import",
        "source_refs": [verification_ref],
        "mime_type": "text/markdown",
        "preview_text": preview_text,
        "source_import_payload": source_import_payload,
        "verification_ref": verification_ref,
        "content_hash": artifact_candidate_content_hash(preview_text),
        "mission_id": "mission-source",
        "operation_key": "source-import-op",
        "materialized": False,
    }
    ref = artifact_candidate_ref(metadata)
    return ref, SimpleNamespace(
        mission_id="mission-source",
        item_type="artifact",
        seq=8,
        producer="tool_orchestrator",
        operation_id="source-import-op",
        payload_json={
            "reference_id": ref,
            "kind": "artifact_candidate",
            "verified": True,
            "uri": url,
            "receipt_operation_key": "source-import-op",
            "metadata": metadata,
        },
    )


@pytest.mark.asyncio
async def test_review_builder_compiles_document_from_accepted_candidate() -> None:
    candidate_ref, candidate_item = _review_candidate_reference()
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-document-1",
                    "candidate_ref": candidate_ref,
                    "output_key": "problem_understanding",
                    "target_kind": "document",
                    "target_room": None,
                    "title": "问题理解（修订版）",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    batch = await StrictReviewCandidateBuilder().build_candidates(request)
    item = batch.items[0]
    descriptor = item.preview_json["materialization"]

    assert item.target_kind == "document"
    assert item.target_room == "documents"
    assert item.title == "问题理解"
    assert descriptor["operation"] == "documents.upsert_prism_file"
    assert descriptor["payload"]["path"] == "问题理解.md"
    assert descriptor["payload"]["content_inline"] == "# 问题理解\n\n完整正文。"
    assert len(descriptor["payload"]["content_hash"]) == 64
    assert item.source_item_seq == 7
    assert item.preview_json["candidate_ref"] == candidate_ref
    assert item.preview_json["source_refs"] == ["prism-file:problem-1"]


@pytest.mark.asyncio
async def test_review_builder_projects_verified_source_candidate_to_library_import() -> None:
    candidate_ref, candidate_item = _source_review_candidate_reference()
    request = SimpleNamespace(
        mission=SimpleNamespace(mission_id="mission-source"),
        stage_id="literature_positioning",
        candidate_json={
            "items": [
                {
                    "candidate_ref": candidate_ref,
                    "output_key": "source.federated_peft",
                    "target_kind": "source",
                    "target_room": "library",
                    "title": "Federated PEFT",
                    "risk_level": "medium",
                    "preview_json": {
                        "materialization": {"operation": "untrusted.write"}
                    },
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    batch = await StrictReviewCandidateBuilder().build_candidates(request)
    item = batch.items[0]
    descriptor = item.preview_json["materialization"]

    assert item.target_kind == "source"
    assert item.target_room == "library"
    assert item.source_item_seq == 8
    assert item.preview_json["artifact_kind"] == "source_import"
    assert descriptor["operation"] == "library.import_source"
    assert descriptor["payload"] == candidate_item.payload_json["metadata"][
        "source_import_payload"
    ]
    assert "untrusted.write" not in str(item.preview_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata_patch", "target_kind", "target_room"),
    [
        ({"verification_ref": "search-receipt:other#source-1"}, "source", "library"),
        ({}, "document", "documents"),
        ({}, "source", "documents"),
    ],
)
async def test_review_builder_rejects_invalid_source_candidate_projection(
    metadata_patch: dict[str, object],
    target_kind: str,
    target_room: str,
) -> None:
    candidate_ref, candidate_item = _source_review_candidate_reference()
    if metadata_patch:
        candidate_item.payload_json["metadata"] = {
            **candidate_item.payload_json["metadata"],
            **metadata_patch,
        }
    request = SimpleNamespace(
        mission=SimpleNamespace(mission_id="mission-source"),
        stage_id="literature_positioning",
        candidate_json={
            "items": [
                {
                    "candidate_ref": candidate_ref,
                    "output_key": "source.federated_peft",
                    "target_kind": target_kind,
                    "target_room": target_room,
                    "title": "Federated PEFT",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    with pytest.raises(MissionProductionConfigurationError):
        await StrictReviewCandidateBuilder().build_candidates(request)


@pytest.mark.asyncio
async def test_review_builder_preserves_complete_academic_visual_provenance() -> None:
    content_hash = "sha256:" + "a" * 64
    preview_hash = "b" * 64
    prompt_hash = "c" * 64
    context_hash = "d" * 64
    overlay_hash = "e" * 64
    candidate_ref = "academic-visual:avc-hybrid"
    metadata = {
        "candidate": {
            "candidate_id": "avc-hybrid",
            "figure_id": "hybrid-method",
            "figure_type": "mechanism_illustration",
            "strategy": "hybrid",
            "evidence_level": "explanatory",
            "review_preview_ref": "mpv1_hybrid_preview",
            "preview_hash": preview_hash,
            "content_hash": content_hash,
            "mime_type": "image/png",
            "width": 1536,
            "height": 1024,
            "renderer_id": "gpt-image-2+deterministic-overlay",
            "renderer_version": "wenjin.academic_visual.prompt.v1",
            "provider_model": "gpt-image-2",
            "prompt_contract_version": "wenjin.academic_visual.prompt.v1",
            "source_prompt_hash": prompt_hash,
            "context_hash": context_hash,
            "source_refs": ["source:paper-1"],
            "dataset_refs": [],
            "source_content_hashes": {},
            "dataset_content_hashes": {},
            "ai_generated": True,
            "overlay_manifest_hash": overlay_hash,
            "quality_receipt": {
                "decoded": True,
                "nonblank": True,
                "requested_quality": "high",
                "preview_expires_at": "2026-07-17T00:00:00+00:00",
            },
            "warnings": ["AI-generated explanatory illustration"],
        },
        "manifest": {
            "caption": "Hybrid method overview",
            "alt_text": "Method nodes connected from left to right",
            "source_prompt_hash": prompt_hash,
            "prompt_contract_version": "wenjin.academic_visual.prompt.v1",
            "context_hash": context_hash,
            "ai_generated": True,
            "overlay_manifest_hash": overlay_hash,
        },
    }
    candidate_item = SimpleNamespace(
        mission_id="mission-visual",
        item_type="artifact",
        seq=12,
        payload_json={
            "reference_id": candidate_ref,
            "kind": "academic_visual_candidate",
            "verified": True,
            "metadata": metadata,
        },
    )
    request = SimpleNamespace(
        mission=SimpleNamespace(mission_id="mission-visual"),
        stage_id="visuals",
        candidate_json={
            "items": [
                {
                    "candidate_ref": candidate_ref,
                    "output_key": "visual.hybrid_method",
                    "target_kind": "workspace_asset",
                    "target_room": "assets",
                    "title": "Hybrid method",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    batch = await StrictReviewCandidateBuilder().build_candidates(request)
    preview = batch.items[0].preview_json
    asset_metadata = preview["materialization"]["payload"]["metadata_json"]

    for projection in (preview, asset_metadata):
        assert projection["source_prompt_hash"] == prompt_hash
        assert projection["prompt_contract_version"] == (
            "wenjin.academic_visual.prompt.v1"
        )
        assert projection["context_hash"] == context_hash
        assert projection["dimensions"] == {"width": 1536, "height": 1024}
        assert projection["quality_receipt"]["requested_quality"] == "high"
        assert projection["ai_generated"] is True
        assert projection["overlay_manifest_hash"] == overlay_hash
    assert asset_metadata["mission_id"] == "mission-visual"
    assert asset_metadata["source_item_seq"] == 12
    assert asset_metadata["content_hash"] == preview_hash
    assert asset_metadata["candidate_content_hash"] == content_hash


def test_current_figure_projection_does_not_recognize_legacy_chart_taxonomy() -> None:
    assert _academic_visual_artifact_kind({"figure_type": "data_plot"}) == "chart"
    assert _academic_visual_artifact_kind({"figure_type": "statistical_chart"}) == "chart"
    assert _academic_visual_artifact_kind({"figure_type": "line_chart"}) == "figure"
    assert _academic_visual_artifact_kind({"figure_type": "bar_chart"}) == "figure"


def test_deterministic_visual_asset_provenance_preserves_source_code() -> None:
    provenance = _academic_visual_asset_provenance(
        item=SimpleNamespace(mission_id="mission-1", seq=8),
        visual={
            "content_hash": "sha256:" + "a" * 64,
            "source_code_hash": "b" * 64,
            "context_hash": "c" * 64,
            "width": 1200,
            "height": 800,
            "ai_generated": False,
        },
        manifest={
            "source_code_ref": "sandbox-script:sha256:" + "b" * 64,
            "source_code_hash": "b" * 64,
            "context_hash": "c" * 64,
            "ai_generated": False,
        },
        quality_receipt={"decoded": True, "nonblank": True},
    )

    assert provenance["source_code_hash"] == "b" * 64
    assert provenance["source_code_ref"] == "sandbox-script:sha256:" + "b" * 64
    assert provenance["context_hash"] == "c" * 64
    assert provenance["dimensions"] == {"width": 1200, "height": 800}
    assert provenance["ai_generated"] is False


@pytest.mark.asyncio
async def test_review_builder_rejects_target_ref_used_as_base_revision() -> None:
    candidate_ref, candidate_item = _review_candidate_reference()
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-document-1",
                    "candidate_ref": candidate_ref,
                    "output_key": "problem_understanding",
                    "target_kind": "document",
                    "target_room": "documents",
                    "target_ref": "prism-file:file-1",
                    "base_revision_ref": "prism-file:file-1",
                    "base_hash": "old-hash",
                    "title": "问题理解",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="base revision must come from tool metadata",
    ):
        await StrictReviewCandidateBuilder().build_candidates(request)


@pytest.mark.asyncio
async def test_review_builder_rejects_semantic_type_as_unmaterializable_target() -> None:
    candidate_ref, candidate_item = _review_candidate_reference()
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-semantic-1",
                    "candidate_ref": candidate_ref,
                    "output_key": "problem_understanding",
                    "target_kind": "modeling_problem_brief",
                    "title": "问题理解",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[candidate_item],
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="can only materialize as documents",
    ):
        await StrictReviewCandidateBuilder().build_candidates(request)


@pytest.mark.asyncio
async def test_review_builder_rejects_unverified_candidate_ref() -> None:
    candidate_ref, _candidate_item = _review_candidate_reference()
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-document-sources",
                    "candidate_ref": candidate_ref,
                    "output_key": "question.solution",
                    "target_kind": "document",
                    "target_room": "documents",
                    "title": "问题求解",
                    "risk_level": "high",
                }
            ]
        },
        accepted_candidate_refs=[candidate_ref],
        reference_items=[],
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="verified internal candidate",
    ):
        await StrictReviewCandidateBuilder().build_candidates(request)


@pytest.mark.asyncio
async def test_review_builder_rejects_candidate_not_accepted_for_stage() -> None:
    candidate_ref, candidate_item = _review_candidate_reference()
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-unaccepted",
                    "candidate_ref": candidate_ref,
                    "output_key": "problem_understanding",
                    "target_kind": "document",
                    "title": "问题理解",
                    "risk_level": "medium",
                }
            ]
        },
        accepted_candidate_refs=["artifact-candidate:" + "f" * 64],
        reference_items=[candidate_item],
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="accepted for this stage",
    ):
        await StrictReviewCandidateBuilder().build_candidates(request)
