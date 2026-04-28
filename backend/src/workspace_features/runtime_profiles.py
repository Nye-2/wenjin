"""Runtime profiles for canonical workspace features.

The profile is the source of truth for whether a feature runs as a plain
workflow or may enter a Compute/agentic execution surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.workspace_features.registry import iter_workspace_features


class FeatureRuntimeMode(StrEnum):
    """Execution mode for a workspace feature."""

    CHAT_ONLY = "chat_only"
    DETERMINISTIC = "deterministic"
    COMPUTE_WORKFLOW = "compute_workflow"
    COMPUTE_AGENTIC = "compute_agentic"


@dataclass(frozen=True, slots=True)
class FeatureRuntimeProfile:
    """Runtime policy for one canonical workspace feature."""

    workspace_type: str
    feature_id: str
    runtime_mode: FeatureRuntimeMode
    requires_compute: bool = True
    requires_sandbox: bool = False
    allowed_subagents: tuple[str, ...] = ()
    max_subagents: int = 0
    agent_harness_provider: str | None = None
    output_contract: str = "feature_result"
    review_gate: str | None = None

    @property
    def is_agentic(self) -> bool:
        return self.runtime_mode == FeatureRuntimeMode.COMPUTE_AGENTIC


_WORKFLOW_DEFAULT = FeatureRuntimeProfile(
    workspace_type="*",
    feature_id="*",
    runtime_mode=FeatureRuntimeMode.COMPUTE_WORKFLOW,
)


def _profile(
    workspace_type: str,
    feature_id: str,
    *,
    runtime_mode: FeatureRuntimeMode = FeatureRuntimeMode.COMPUTE_WORKFLOW,
    requires_sandbox: bool = False,
    allowed_subagents: tuple[str, ...] = (),
    max_subagents: int = 0,
    agent_harness_provider: str | None = None,
    output_contract: str = "feature_result",
    review_gate: str | None = None,
) -> FeatureRuntimeProfile:
    return FeatureRuntimeProfile(
        workspace_type=workspace_type,
        feature_id=feature_id,
        runtime_mode=runtime_mode,
        requires_compute=True,
        requires_sandbox=requires_sandbox,
        allowed_subagents=allowed_subagents,
        max_subagents=max_subagents,
        agent_harness_provider=agent_harness_provider,
        output_contract=output_contract,
        review_gate=review_gate,
    )


_AGENTIC_RESEARCH_SUBAGENTS = (
    "scout",
    "trend_spotter",
    "gap_miner",
    "synthesizer",
)
_AGENTIC_FIGURE_SUBAGENTS = (
    "figure_planner",
    "analyst",
)


_PROFILE_OVERRIDES: dict[tuple[str, str], FeatureRuntimeProfile] = {
    ("thesis", "deep_research"): _profile(
        "thesis",
        "deep_research",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        allowed_subagents=_AGENTIC_RESEARCH_SUBAGENTS,
        max_subagents=4,
        output_contract="evidence_pack",
    ),
    ("sci", "literature_search"): _profile(
        "sci",
        "literature_search",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        allowed_subagents=_AGENTIC_RESEARCH_SUBAGENTS,
        max_subagents=4,
        output_contract="evidence_pack",
    ),
    ("proposal", "background_research"): _profile(
        "proposal",
        "background_research",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        allowed_subagents=_AGENTIC_RESEARCH_SUBAGENTS,
        max_subagents=4,
        output_contract="evidence_pack",
    ),
    ("patent", "prior_art_search"): _profile(
        "patent",
        "prior_art_search",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        allowed_subagents=_AGENTIC_RESEARCH_SUBAGENTS,
        max_subagents=4,
        output_contract="evidence_pack",
    ),
}

for _workspace_type in ("thesis", "sci", "proposal", "software_copyright", "patent"):
    _PROFILE_OVERRIDES[(_workspace_type, "figure_generation")] = _profile(
        _workspace_type,
        "figure_generation",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        requires_sandbox=True,
        allowed_subagents=_AGENTIC_FIGURE_SUBAGENTS,
        max_subagents=2,
        output_contract="draft_pack",
        review_gate="artifact_preview",
    )


def get_feature_runtime_profile(
    workspace_type: str,
    feature_id: str,
) -> FeatureRuntimeProfile | None:
    """Return the runtime profile for a canonical feature."""
    normalized_workspace_type = str(workspace_type or "").strip()
    normalized_feature_id = str(feature_id or "").strip()
    if not normalized_workspace_type or not normalized_feature_id:
        return None
    feature_keys = {
        (feature.workspace_type, feature.id)
        for feature in iter_workspace_features()
    }
    key = (normalized_workspace_type, normalized_feature_id)
    if key not in feature_keys:
        return None
    override = _PROFILE_OVERRIDES.get(key)
    if override is not None:
        return override
    return FeatureRuntimeProfile(
        workspace_type=normalized_workspace_type,
        feature_id=normalized_feature_id,
        runtime_mode=_WORKFLOW_DEFAULT.runtime_mode,
        requires_compute=_WORKFLOW_DEFAULT.requires_compute,
        requires_sandbox=_WORKFLOW_DEFAULT.requires_sandbox,
        allowed_subagents=_WORKFLOW_DEFAULT.allowed_subagents,
        max_subagents=_WORKFLOW_DEFAULT.max_subagents,
        agent_harness_provider=_WORKFLOW_DEFAULT.agent_harness_provider,
        output_contract=_WORKFLOW_DEFAULT.output_contract,
        review_gate=_WORKFLOW_DEFAULT.review_gate,
    )


def iter_feature_runtime_profiles() -> tuple[FeatureRuntimeProfile, ...]:
    """Return profiles for all registered workspace features."""
    profiles: list[FeatureRuntimeProfile] = []
    for feature in iter_workspace_features():
        profile = get_feature_runtime_profile(feature.workspace_type, feature.id)
        if profile is not None:
            profiles.append(profile)
    return tuple(profiles)

