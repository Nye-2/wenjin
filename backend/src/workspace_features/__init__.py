"""Workspace feature registry exports."""

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
from .runtime import (
    WorkspaceFeatureExecutionContext,
    execute_registered_feature,
    list_registered_handler_keys,
    register_feature_handler,
)

__all__ = [
    "CANONICAL_WORKSPACE_TYPES",
    "FeatureArtifactDraft",
    "FeatureArtifactReference",
    "FeatureStageDefinition",
    "WorkspaceFeatureDefinition",
    "WorkspaceFeatureExecutionContext",
    "WorkspaceFeatureExecutionResult",
    "execute_registered_feature",
    "get_workspace_feature",
    "get_workspace_feature_by_handler",
    "iter_workspace_features",
    "list_registered_handler_keys",
    "list_workspace_features",
    "register_feature_handler",
]
