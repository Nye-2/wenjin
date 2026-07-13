from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.contracts.stage_acceptance import StageAcceptanceContract
from src.dataservice_client.contracts.catalog import MissionPolicyPayload, WorkerSkillPayload
from src.dataservice_client.contracts.mission import MissionItemPayload
from src.mission_runtime.contracts import StageQualityRequest
from src.mission_runtime.production import (
    CeleryMissionWakeupPublisher,
    MissionProductionConfigurationError,
    PinnedMissionStartContext,
    PinnedStageAssessmentBuilder,
    PinnedStageContractResolver,
    PinnedToolPolicyResolver,
    StrictReviewCandidateBuilder,
    _resolve_tool_groups,
    require_mission_model_profile,
    require_native_search_capability,
)
from src.models.capability_profile import WebSearchAPI, gpt56_release_assessment
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
)
from src.services.skill_loader import SkillLoader
from src.tools.orchestrator import ToolCallerKind

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
            "schema_version": "stage_acceptance_contract.v1",
            "contract_id": "test.scope",
            "version": 1,
            "mission_policy_id": "test-policy",
            "workspace_type": "sci",
            "stage_id": "scope",
            "stage_goal": "Produce a grounded scope.",
            "minimum_criteria": [{"criterion_id": "bounded", "description": "The scope is bounded."}],
            "required_artifacts": [{"kind": "research_brief"}],
            "reviewer_roles": ["research_scope_reviewer"],
            "allowed_actions_if_failed": ["revise_existing", "stop_execution"],
            "advance_condition": "The scope passes.",
            "stop_condition": "The scope cannot be repaired.",
        }
    )


@pytest.mark.asyncio
async def test_stage_assessment_rejects_model_self_certification(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    mission = mission.model_copy(
        update={
            "snapshot_json": {
                "review_candidate_manifests": {
                    "review-1": {
                        "artifact_kind": "research_brief",
                        "preview_hash": "a" * 64,
                        "status": "pending",
                    }
                }
            }
        }
    )
    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-1",
            stage_id="scope",
            candidate_refs=["review-1"],
            assessment_json={
                "criterion_assessments": [
                    {
                        "criterion_id": "bounded",
                        "status": "pass",
                        "supporting_refs": ["review-1"],
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "review-1",
                        "kind": "research_brief",
                        "content_hash": "a" * 64,
                    }
                ],
                "critiques": [
                    {
                        "reviewer_role": "research_scope_reviewer",
                        "verdict": "pass",
                        "criterion_ids": ["bounded"],
                    }
                ],
            },
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert [item.artifact_id for item in assessment.artifacts] == ["review-1"]
    assert assessment.critiques == ()


@pytest.mark.asyncio
async def test_stage_assessment_accepts_persisted_upstream_candidate_refs(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    mission = mission.model_copy(
        update={
            "snapshot_json": {
                "review_candidate_manifests": {
                    "review-1": {
                        "artifact_kind": "research_brief",
                        "preview_hash": "a" * 64,
                        "status": "pending",
                    },
                    "upstream-review": {
                        "artifact_kind": "problem_brief",
                        "preview_hash": "b" * 64,
                        "status": "pending",
                    },
                }
            }
        }
    )

    assessment = await PinnedStageAssessmentBuilder().build(
        StageQualityRequest(
            mission=mission,
            operation_id="quality-1",
            stage_id="scope",
            candidate_refs=["review-1"],
            assessment_json={
                "criterion_assessments": [
                    {
                        "criterion_id": "bounded",
                        "status": "pass",
                        "supporting_refs": ["review-1", "upstream-review"],
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "review-1",
                        "kind": "research_brief",
                        "content_hash": "a" * 64,
                    }
                ],
            },
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert assessment.criterion_assessments[0].supporting_refs == (
        "review-1",
        "upstream-review",
    )


@pytest.mark.asyncio
async def test_stage_assessment_accepts_persisted_independent_review(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request(mission_policy_id="test-policy"))
    mission = await deps["store"].get(receipt.mission_id)
    assert mission is not None
    mission = mission.model_copy(
        update={
            "snapshot_json": {
                "review_candidate_manifests": {
                    "review-1": {
                        "artifact_kind": "research_brief",
                        "preview_hash": "a" * 64,
                        "status": "pending",
                    }
                }
            }
        }
    )
    reviewer_item = MissionItemPayload(
        id="item-reviewer",
        mission_id=mission.mission_id,
        seq=1,
        item_type="subagent_completed",
        operation_id="reviewer-op",
        phase="completed",
        stage_id="scope",
        producer="subagent_runtime",
        payload_json={
            "jobs": [
                {
                    "status": "completed",
                    "role_label": "research_scope_reviewer",
                    "evidence_refs": ["mission-review:review-1"],
                    "result_json": {
                        "reviewer_role": "research_scope_reviewer",
                        "verdict": "pass",
                        "criterion_ids": ["bounded"],
                        "reviewed_candidate_refs": ["mission-review:review-1"],
                        "note": "The bounded scope is explicit.",
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
            candidate_refs=["review-1"],
            assessment_json={
                "criterion_assessments": [
                    {
                        "criterion_id": "bounded",
                        "status": "pass",
                        "supporting_refs": ["review-1"],
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "review-1",
                        "kind": "research_brief",
                        "content_hash": "a" * 64,
                    }
                ],
            },
            recent_items=[reviewer_item],
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert [item.reviewer_role for item in assessment.critiques] == ["research_scope_reviewer"]


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
        item_type="tool_result",
        operation_id="sandbox-op",
        phase="completed",
        stage_id="scope",
        producer="tool_orchestrator",
        payload_json={
            "research_tool_outcome": {
                "operation_id": "sandbox-op",
                "operation_key": "sandbox-op-key",
                "producer": "sandbox.run_python",
                "tool_id": "sandbox.run_python",
                "tool_version": "1",
                "status": "success",
                "observed_at": mission.created_at.isoformat(),
                "summary": "Verified computation",
                "evidence_refs": [],
                "source_refs": [],
                "artifact_refs": [
                    {
                        "ref_id": "sandbox-artifact:verified-1",
                        "kind": "sandbox_artifact_manifest",
                        "uri": None,
                        "title": "result.json",
                        "metadata": {},
                    }
                ],
                "confidence": 1.0,
                "risk_level": "low",
                "verification_status": "verified",
                "recommended_next_action": None,
                "payload_ref": None,
                "recoverable_by_model": False,
                "retry_after_seconds": None,
            }
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
            recent_items=[tool_item],
            deadline_monotonic=100,
        ),
        _quality_contract(),
    )

    assert assessment.evidence[0].status == "verified"
    assert assessment.evidence[0].surface == "experiment_reproducibility"


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
    assessment = gpt56_release_assessment("gpt-5.6-sol")
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
    resolver = PinnedMissionStartContext(PolicyDataService([policy_record("sci_research")]))
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
    assert set(runtime["required_stage_ids"]).issubset(runtime["stage_contracts"])
    assert set(runtime["worker_skill_snapshots"]) == set(policy_record("sci_research").to_contract().allowed_worker_skills)
    for skill_id, snapshot in runtime["worker_skill_snapshots"].items():
        assert snapshot["contract"]["id"] == skill_id
        assert len(snapshot["content_hash"]) == 64
        assert set(snapshot["allowed_tool_ids"]).issubset(runtime["tool_policy"]["allowed_tool_ids"])


@pytest.mark.asyncio
async def test_pinned_resolver_resolves_math_per_question_stage(
    monkeypatch,
    runtime_factory,
) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    start_context = PinnedMissionStartContext(PolicyDataService([policy_record("math_modeling_solution")]))
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
async def test_start_context_rejects_routing_policy_hash_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.mission_runtime.production.require_mission_model_profile",
        lambda _model_id: SimpleNamespace(capability_probe_hash="a" * 64),
    )
    resolver = PinnedMissionStartContext(PolicyDataService([policy_record("sci_research")]))

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
        await PinnedMissionStartContext(dataservice).pin(
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
    resolver = PinnedMissionStartContext(PolicyDataService([]))
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
    resolver = PinnedMissionStartContext(PolicyDataService([policy_record(policy_id)]))

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
    resolver = PinnedMissionStartContext(PolicyDataService([policy_record("sci_research")]))

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
async def test_sci_policy_rejects_current_failed_search_probe() -> None:
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

    with pytest.raises(
        MissionProductionConfigurationError,
        match="independent search transport is unavailable",
    ):
        await runtime.start(
            start_request(
                mission_policy_id="sci_research",
                runtime_context_json={
                    "model_capability_profile_hash": model.capability_probe_hash,
                    "policy_content_hash": policy_record("sci_research").content_hash,
                },
            )
        )
    assert not store.runs
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
    request = SimpleNamespace(candidate_json={"items": []})
    with pytest.raises(MissionProductionConfigurationError, match="atomic preview"):
        await StrictReviewCandidateBuilder().build_candidates(request)


@pytest.mark.asyncio
async def test_review_builder_compiles_document_materialization_from_preview() -> None:
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-document-1",
                    "target_kind": "document",
                    "target_room": None,
                    "title": "问题理解",
                    "risk_level": "medium",
                    "preview_json": {
                        "artifact_kind": "modeling_problem_brief",
                        "body": "# 问题理解\n\n完整正文。",
                    },
                }
            ]
        }
    )

    batch = await StrictReviewCandidateBuilder().build_candidates(request)
    item = batch.items[0]
    descriptor = item.preview_json["materialization"]

    assert item.target_kind == "document"
    assert item.target_room == "documents"
    assert descriptor["operation"] == "documents.upsert_prism_file"
    assert descriptor["payload"]["path"] == "问题理解.md"
    assert descriptor["payload"]["content_inline"] == "# 问题理解\n\n完整正文。"
    assert len(descriptor["payload"]["content_hash"]) == 64


@pytest.mark.asyncio
async def test_review_builder_rejects_semantic_type_as_unmaterializable_target() -> None:
    request = SimpleNamespace(
        candidate_json={
            "items": [
                {
                    "review_item_id": "review-semantic-1",
                    "target_kind": "modeling_problem_brief",
                    "title": "问题理解",
                    "risk_level": "medium",
                    "preview_json": {
                        "artifact_kind": "modeling_problem_brief",
                        "body": "# 问题理解",
                    },
                }
            ]
        }
    )

    with pytest.raises(
        MissionProductionConfigurationError,
        match="canonical materialization descriptor",
    ):
        await StrictReviewCandidateBuilder().build_candidates(request)
