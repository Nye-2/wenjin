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

__all__ = [
    "CANONICAL_WORKSPACE_TYPES",
    "FeatureArtifactDraft",
    "FeatureArtifactReference",
    "FeatureStageDefinition",
    "WorkspaceFeatureDefinition",
    "WorkspaceFeatureExecutionResult",
    "FeatureRuntimeMode",
    "FeatureRuntimeProfile",
    "get_workspace_feature",
    "get_workspace_feature_by_handler",
    "get_feature_runtime_profile",
    "iter_feature_runtime_profiles",
    "iter_workspace_features",
    "list_workspace_features",
]
