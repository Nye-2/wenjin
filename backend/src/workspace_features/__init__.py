"""Workspace feature registry exports.

Handler-related exports have been removed per Compute migration.
All features now route through FeatureLeaderRuntime.
"""

from .contracts import (
    FeatureArtifactDraft,
    FeatureArtifactReference,
    WorkspaceFeatureExecutionResult,
)
from .registry import (
    CANONICAL_WORKSPACE_TYPES,
    FeatureStageDefinition,
    WorkspaceFeatureDefinition,
    get_workspace_feature,
    get_workspace_feature_by_handler,
    iter_workspace_features,
    list_workspace_features,
)
from .runtime_profiles import (
    FeatureRuntimeMode,
    FeatureRuntimeProfile,
    get_feature_runtime_profile,
    iter_feature_runtime_profiles,
)
from .skills import (
    WorkspaceThreadSkillDefinition,
    get_default_skill_for_feature,
    get_skill_by_id,
    list_feature_skill_ids,
    list_feature_skills,
    list_workspace_thread_skills,
    resolve_skill_for_feature,
)

__all__ = [
    "CANONICAL_WORKSPACE_TYPES",
    "FeatureArtifactDraft",
    "FeatureArtifactReference",
    "FeatureStageDefinition",
    "WorkspaceFeatureDefinition",
    "WorkspaceThreadSkillDefinition",
    "WorkspaceFeatureExecutionResult",
    "FeatureRuntimeMode",
    "FeatureRuntimeProfile",
    "get_default_skill_for_feature",
    "get_skill_by_id",
    "get_workspace_feature",
    "get_workspace_feature_by_handler",
    "get_feature_runtime_profile",
    "iter_feature_runtime_profiles",
    "iter_workspace_features",
    "list_feature_skill_ids",
    "list_feature_skills",
    "list_workspace_features",
    "list_workspace_thread_skills",
    "resolve_skill_for_feature",
]
