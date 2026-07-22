"""Production composition root for the MissionRuntime graph."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.dataservice_client import AsyncDataServiceClient
from src.mission_runtime.adapters import (
    LangChainSubagentModel,
    MissionItemOperationJournal,
    MissionLeaseFenceAdapter,
    MissionSandboxReceiptStore,
    MissionSubagentRuntimeAdapter,
    MissionSubagentToolAdapter,
    MissionToolOrchestratorAdapter,
    StageAcceptanceAdapter,
    StageAssessmentBuilder,
    StageContractResolver,
    ToolPolicyResolver,
)
from src.mission_runtime.contracts import (
    MISSION_MODEL_COMPLETION_MARGIN_SECONDS,
    SUBAGENT_MODEL_REQUEST_TIMEOUT_SECONDS,
    MissionSliceLimits,
)
from src.mission_runtime.ports import (
    MissionAgentPort,
    MissionEventPublisherPort,
    MissionStartContextPort,
    MissionStorePort,
    MissionWakeupPublisherPort,
    ReviewCandidatePort,
    SystemMissionClock,
)
from src.mission_runtime.production import (
    CeleryMissionWakeupPublisher,
    PinnedMissionStartContext,
    PinnedStageAssessmentBuilder,
    PinnedStageContractResolver,
    PinnedToolPolicyResolver,
    StrictReviewCandidateBuilder,
    StrictToolExecutionGuard,
    WorkspaceMissionEventPublisher,
    build_production_tool_catalog,
    production_agent,
    require_mission_model_profile,
)
from src.mission_runtime.runtime import MissionRuntime
from src.services.model_catalog_cache import resolve_runtime_model_id
from src.subagent_runtime.runtime import SubagentModelPort
from src.tools.orchestrator import (
    ToolCatalog,
    ToolExecutionGuard,
    ToolOrchestrator,
    ToolPolicy,
)


class MissionCompositionConfigurationError(RuntimeError):
    """Raised when a worker has no complete production dependency graph."""


@dataclass(frozen=True, slots=True)
class MissionEffectContext:
    """Store-bound effect ports used to assemble the unique tool catalog."""

    store: MissionStorePort
    lease_guard: MissionLeaseFenceAdapter
    sandbox_receipts: MissionSandboxReceiptStore
    dataservice: AsyncDataServiceClient


ToolCatalogFactory = Callable[[MissionEffectContext], ToolCatalog]
MissionStartContextFactory = Callable[[ToolCatalog], MissionStartContextPort]


@dataclass(frozen=True, slots=True)
class MissionCompositionDependencies:
    agent: MissionAgentPort
    start_context_factory: MissionStartContextFactory
    tool_catalog_factory: ToolCatalogFactory
    tool_guard: ToolExecutionGuard
    tool_policy_resolver: ToolPolicyResolver
    stage_contract_resolver: StageContractResolver
    stage_assessment_builder: StageAssessmentBuilder
    review_candidates: ReviewCandidatePort
    events: MissionEventPublisherPort
    wakeups: MissionWakeupPublisherPort
    subagent_model: SubagentModelPort | None = None
    limits: MissionSliceLimits | None = None
    subagent_max_concurrency: int = 4
    subagent_max_jobs_per_batch: int = 4


async def build_production_mission_runtime(
    dataservice: AsyncDataServiceClient,
) -> MissionRuntime:
    """Build the complete graph directly; no process-global configuration seam."""
    try:
        model_id = resolve_runtime_model_id(None)
        require_mission_model_profile(model_id)
    except Exception as exc:
        raise MissionCompositionConfigurationError("MissionRuntime production model capabilities are unavailable") from exc
    return compose_mission_runtime(
        dataservice,
        MissionCompositionDependencies(
            agent=production_agent(),
            start_context_factory=lambda catalog: PinnedMissionStartContext(
                dataservice,
                tool_catalog=catalog,
            ),
            tool_catalog_factory=build_production_tool_catalog,
            tool_guard=StrictToolExecutionGuard(),
            tool_policy_resolver=PinnedToolPolicyResolver(),
            stage_contract_resolver=PinnedStageContractResolver(),
            stage_assessment_builder=PinnedStageAssessmentBuilder(),
            review_candidates=StrictReviewCandidateBuilder(),
            events=WorkspaceMissionEventPublisher(),
            wakeups=CeleryMissionWakeupPublisher(),
            limits=MissionSliceLimits(max_model_turns=1),
        ),
    )


def compose_mission_runtime(
    dataservice: AsyncDataServiceClient,
    dependencies: MissionCompositionDependencies,
) -> MissionRuntime:
    store = dataservice.missions
    limits = dependencies.limits or MissionSliceLimits()
    fence = MissionLeaseFenceAdapter(
        store,
        lease_ttl_seconds=limits.lease_ttl_seconds,
    )
    effect_context = MissionEffectContext(
        store=store,
        lease_guard=fence,
        sandbox_receipts=MissionSandboxReceiptStore(store),
        dataservice=dataservice,
    )
    tool_catalog = dependencies.tool_catalog_factory(effect_context)
    if not tool_catalog.frozen:
        raise MissionCompositionConfigurationError("Mission tool catalog must be assembled and frozen before worker startup")
    operation_ttl_seconds = max(
        5,
        limits.lease_ttl_seconds - int(limits.heartbeat_interval_seconds),
    )
    journal = MissionItemOperationJournal(
        store,
        operation_ttl_seconds=operation_ttl_seconds,
    )
    orchestrator = ToolOrchestrator(
        catalog=tool_catalog,
        journal=journal,
        lease_fence=fence,
        guard=dependencies.tool_guard,
    )
    for descriptor in tool_catalog.descriptors():
        required_budget = orchestrator.required_budget_seconds(
            descriptor.tool_id,
            ToolPolicy(
                policy_ref=f"catalog:{tool_catalog.descriptor_snapshot_hash()}",
                allowed_tool_ids=(descriptor.tool_id,),
                execution_limits=tool_catalog.execution_limits(
                    (descriptor.tool_id,)
                ),
            ),
        )
        if required_budget > (
            limits.wall_time_seconds - limits.shutdown_margin_seconds
        ):
            raise MissionCompositionConfigurationError(
                "Tool execution budget exceeds the safe durable Mission window: "
                f"{descriptor.tool_id}"
            )
        if required_budget > operation_ttl_seconds:
            raise MissionCompositionConfigurationError(
                f"Tool execution budget exceeds its durable operation claim: {descriptor.tool_id}"
            )
    tools = MissionToolOrchestratorAdapter(
        store=store,
        orchestrator=orchestrator,
        policy_resolver=dependencies.tool_policy_resolver,
    )
    subagent_tools = MissionSubagentToolAdapter(
        store=store,
        orchestrator=orchestrator,
        policy_resolver=dependencies.tool_policy_resolver,
    )
    subagents = MissionSubagentRuntimeAdapter(
        store=store,
        model=dependencies.subagent_model or LangChainSubagentModel(),
        tools=subagent_tools,
        max_concurrency=dependencies.subagent_max_concurrency,
        max_jobs_per_batch=dependencies.subagent_max_jobs_per_batch,
        model_call_timeout_seconds=(
            SUBAGENT_MODEL_REQUEST_TIMEOUT_SECONDS
            if dependencies.subagent_model is None
            else 0.0
        ),
        model_call_completion_margin_seconds=(
            MISSION_MODEL_COMPLETION_MARGIN_SECONDS
            if dependencies.subagent_model is None
            else 0.0
        ),
        events=dependencies.events,
        clock=SystemMissionClock(),
    )
    quality = StageAcceptanceAdapter(
        contracts=dependencies.stage_contract_resolver,
        assessments=dependencies.stage_assessment_builder,
    )
    return MissionRuntime(
        store=store,
        agent=dependencies.agent,
        start_context=dependencies.start_context_factory(tool_catalog),
        tools=tools,
        subagents=subagents,
        quality=quality,
        review_candidates=dependencies.review_candidates,
        events=dependencies.events,
        wakeups=dependencies.wakeups,
        limits=limits,
    )


__all__ = [
    "MissionCompositionConfigurationError",
    "MissionCompositionDependencies",
    "MissionEffectContext",
    "MissionStartContextFactory",
    "ToolCatalogFactory",
    "build_production_mission_runtime",
    "compose_mission_runtime",
]
