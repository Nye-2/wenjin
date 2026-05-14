"""Execution contracts for workspace feature handlers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class FeatureArtifactDraft:
    """Artifact draft produced by a workspace feature handler."""

    type: str
    content: dict[str, Any]
    title: str | None = None
    created_by_skill: str | None = None
    parent_artifact_id: str | None = None


@dataclass(slots=True, frozen=True)
class FeatureArtifactReference:
    """Persisted artifact reference returned to the task result."""

    id: str
    type: str
    title: str | None = None


@dataclass(slots=True)
class WorkspaceFeatureExecutionResult:
    """Normalized result contract for non-thesis workspace feature handlers."""

    message: str
    success: bool = True
    artifacts: list[FeatureArtifactReference] = field(default_factory=list)
    refresh_targets: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_payload(
        self,
        *,
        feature_id: str,
        feature_name: str,
        workspace_type: str,
        agent: str | None,
    ) -> dict[str, Any]:
        """Serialize the normalized result to the task result payload."""
        return {
            "success": self.success,
            "feature_id": feature_id,
            "feature_name": feature_name,
            "workspace_type": workspace_type,
            "agent": agent,
            "message": self.message,
            "artifacts": [
                {
                    "id": artifact.id,
                    "type": artifact.type,
                    "title": artifact.title,
                }
                for artifact in self.artifacts
            ],
            "refresh_targets": self.refresh_targets,
            "next_steps": self.next_steps,
            "data": self.data,
        }
