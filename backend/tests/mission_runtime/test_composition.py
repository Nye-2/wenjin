from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from src.contracts.model_usage import ModelUsage, ModelUsageReceipt
from src.mission_runtime.adapters import (
    MissionSandboxReceiptStore,
    MissionSubagentRuntimeAdapter,
    MissionToolOrchestratorAdapter,
    StageAcceptanceAdapter,
)
from src.mission_runtime.composition import (
    MissionCompositionConfigurationError,
    MissionCompositionDependencies,
    build_production_mission_runtime,
    compose_mission_runtime,
)
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
)
from src.subagent_runtime.contracts import SubagentAction, SubagentModelTurn
from src.tools.orchestrator import (
    SideEffectClass,
    ToolCallerKind,
    ToolCatalog,
    ToolExecutionLimit,
    ToolGuardDecision,
    ToolHandlerResult,
    ToolKind,
    ToolOutcomeStatus,
    ToolPolicy,
    build_tool_registration,
)
from src.tools.orchestrator.catalog import schema_hash
from tests.models.capability_fixtures import verified_capability_assessment

from .conftest import (
    FakeEvents,
    FakeMissionStore,
    FakeReviewCandidates,
    FakeStartContext,
    FakeWakeups,
    MutableClock,
    ScriptedAgent,
)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str


class _Guard:
    async def preflight(self, **_kwargs):
        return ToolGuardDecision(allowed=True)


def _research_read_registration():
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="read completed",
        )

    return build_tool_registration(
        tool_id="research.read",
        tool_version="1",
        kind=ToolKind.READ,
        input_model=_Input,
        handler=handler,
        side_effect_class=SideEffectClass.NONE,
        allowed_callers=(
            ToolCallerKind.WORKSPACE_AGENT,
            ToolCallerKind.SUBAGENT,
        ),
        timeout_seconds=60,
        max_attempts=1,
    )


class _Policy:
    async def resolve(self, mission, *, caller_kind, allowed_tools=None):
        descriptor = _research_read_registration().descriptor
        return ToolPolicy(
            policy_ref="policy:1",
            allowed_tool_ids=allowed_tools or ("research.read",),
            execution_limits=(
                ToolExecutionLimit(
                    tool_id="research.read",
                    descriptor_schema_hash=descriptor.schema_hash,
                    descriptor_hash=schema_hash(
                        descriptor.model_dump(mode="json")
                    ),
                    timeout_seconds=60,
                    max_attempts=1,
                ),
            ),
        )


class _UnusedContracts:
    async def resolve(self, mission, stage_id):
        raise AssertionError("quality contract should not be loaded during composition")


class _UnusedAssessments:
    async def build(self, request, contract):
        raise AssertionError("assessment should not be built during composition")


class _Model:
    async def next_action(self, job, steps, tool_results):
        return SubagentModelTurn(
            action=SubagentAction(kind="complete", summary="done", result_json={}),
            usage_receipt=ModelUsageReceipt(
                model_id=job.model_id,
                provider_response_id="composition-response",
                usage=ModelUsage(input_tokens=4, output_tokens=1, total_tokens=5),
            ),
        )


def _catalog(effect_context) -> ToolCatalog:
    assert isinstance(effect_context.sandbox_receipts, MissionSandboxReceiptStore)
    return ToolCatalog([_research_read_registration()]).freeze()


def test_composition_builds_every_runtime_port_from_one_store_bound_graph() -> None:
    store = FakeMissionStore(MutableClock())
    dataservice = SimpleNamespace(missions=store)
    runtime = compose_mission_runtime(
        dataservice,  # type: ignore[arg-type]
        MissionCompositionDependencies(
            agent=ScriptedAgent([]),
            start_context_factory=lambda _catalog: FakeStartContext(),
            tool_catalog_factory=_catalog,
            tool_guard=_Guard(),
            tool_policy_resolver=_Policy(),
            stage_contract_resolver=_UnusedContracts(),
            stage_assessment_builder=_UnusedAssessments(),
            review_candidates=FakeReviewCandidates(),
            events=FakeEvents(),
            wakeups=FakeWakeups(),
            subagent_model=_Model(),
        ),
    )

    assert runtime.store is store
    assert isinstance(runtime.tools, MissionToolOrchestratorAdapter)
    assert isinstance(runtime.subagents, MissionSubagentRuntimeAdapter)
    assert isinstance(runtime.quality, StageAcceptanceAdapter)


def test_composition_rejects_catalog_budget_larger_than_mission_slice() -> None:
    def oversized_catalog(_effect_context) -> ToolCatalog:
        async def handler(_operation, _arguments):
            return ToolHandlerResult(
                status=ToolOutcomeStatus.SUCCESS,
                summary="read completed",
            )

        return ToolCatalog(
            [
                build_tool_registration(
                    tool_id="research.read",
                    tool_version="1",
                    kind=ToolKind.READ,
                    input_model=_Input,
                    handler=handler,
                    side_effect_class=SideEffectClass.NONE,
                    allowed_callers=(ToolCallerKind.WORKSPACE_AGENT,),
                    timeout_seconds=171,
                    max_attempts=1,
                )
            ]
        ).freeze()

    store = FakeMissionStore(MutableClock())
    with pytest.raises(
        MissionCompositionConfigurationError,
        match="exceeds the durable Mission slice",
    ):
        compose_mission_runtime(
            SimpleNamespace(missions=store),  # type: ignore[arg-type]
            MissionCompositionDependencies(
                agent=ScriptedAgent([]),
                start_context_factory=lambda _catalog: FakeStartContext(),
                tool_catalog_factory=oversized_catalog,
                tool_guard=_Guard(),
                tool_policy_resolver=_Policy(),
                stage_contract_resolver=_UnusedContracts(),
                stage_assessment_builder=_UnusedAssessments(),
                review_candidates=FakeReviewCandidates(),
                events=FakeEvents(),
                wakeups=FakeWakeups(),
                subagent_model=_Model(),
            ),
        )


def _verified_model() -> RuntimeModelConfig:
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
async def test_production_builder_requires_no_process_global_configuration() -> None:
    reset_model_catalog_cache()
    install_model_catalog_snapshot([_verified_model()])
    store = FakeMissionStore(MutableClock())
    runtime = await build_production_mission_runtime(
        SimpleNamespace(missions=store)  # type: ignore[arg-type]
    )
    assert runtime.store is store
    assert runtime.start_context.__class__.__name__ == "PinnedMissionStartContext"


@pytest.mark.asyncio
async def test_production_builder_fails_closed_without_verified_model_profile() -> None:
    reset_model_catalog_cache()
    with pytest.raises(
        MissionCompositionConfigurationError,
        match="model capabilities are unavailable",
    ):
        await build_production_mission_runtime(SimpleNamespace())  # type: ignore[arg-type]
