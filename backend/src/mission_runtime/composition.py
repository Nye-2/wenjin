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
from src.mission_runtime.contracts import MissionSliceLimits
from src.mission_runtime.ports import (
    BillingPort,
    MissionAgentPort,
    MissionEventPublisherPort,
    MissionStartContextPort,
    MissionStorePort,
    MissionWakeupPublisherPort,
    ReviewCandidatePort,
)
from src.mission_runtime.production import (
    CeleryMissionWakeupPublisher,
    MissionCreditBilling,
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
from src.tools.orchestrator import ToolCatalog, ToolExecutionGuard, ToolOrchestrator


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


@dataclass(frozen=True, slots=True)
class MissionCompositionDependencies:
    agent: MissionAgentPort
    start_context: MissionStartContextPort
    tool_catalog_factory: ToolCatalogFactory
    tool_guard: ToolExecutionGuard
    tool_policy_resolver: ToolPolicyResolver
    stage_contract_resolver: StageContractResolver
    stage_assessment_builder: StageAssessmentBuilder
    review_candidates: ReviewCandidatePort
    billing: BillingPort
    events: MissionEventPublisherPort
    wakeups: MissionWakeupPublisherPort
    subagent_model: SubagentModelPort | None = None
    limits: MissionSliceLimits | None = None
    subagent_max_concurrency: int = 4
    subagent_max_jobs_per_batch: int = 8


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
            start_context=PinnedMissionStartContext(dataservice),
            tool_catalog_factory=build_production_tool_catalog,
            tool_guard=StrictToolExecutionGuard(),
            tool_policy_resolver=PinnedToolPolicyResolver(),
            stage_contract_resolver=PinnedStageContractResolver(),
            stage_assessment_builder=PinnedStageAssessmentBuilder(),
            review_candidates=StrictReviewCandidateBuilder(),
            billing=MissionCreditBilling(dataservice),
            events=WorkspaceMissionEventPublisher(),
            wakeups=CeleryMissionWakeupPublisher(),
        ),
    )


def compose_mission_runtime(
    dataservice: AsyncDataServiceClient,
    dependencies: MissionCompositionDependencies,
) -> MissionRuntime:
    store = dataservice.missions
    fence = MissionLeaseFenceAdapter(store)
    effect_context = MissionEffectContext(
        store=store,
        lease_guard=fence,
        sandbox_receipts=MissionSandboxReceiptStore(store),
        dataservice=dataservice,
    )
    tool_catalog = dependencies.tool_catalog_factory(effect_context)
    if not tool_catalog.frozen:
        raise MissionCompositionConfigurationError("Mission tool catalog must be assembled and frozen before worker startup")
    limits = dependencies.limits or MissionSliceLimits()
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
    tools = MissionToolOrchestratorAdapter(
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
    )
    quality = StageAcceptanceAdapter(
        contracts=dependencies.stage_contract_resolver,
        assessments=dependencies.stage_assessment_builder,
    )
    return MissionRuntime(
        store=store,
        agent=dependencies.agent,
        start_context=dependencies.start_context,
        tools=tools,
        subagents=subagents,
        quality=quality,
        review_candidates=dependencies.review_candidates,
        billing=dependencies.billing,
        events=dependencies.events,
        wakeups=dependencies.wakeups,
        limits=limits,
    )


__all__ = [
    "MissionCompositionConfigurationError",
    "MissionCompositionDependencies",
    "MissionEffectContext",
    "ToolCatalogFactory",
    "build_production_mission_runtime",
    "compose_mission_runtime",
]
