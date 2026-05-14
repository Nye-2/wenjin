"""Application-layer command objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureLaunchCommand:
    """Input command for feature launch/resume through FeatureIngressService."""

    workspace_id: str
    feature_id: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    thread_id: str | None = None
    skill_id: str | None = None
    launch_source: str = "thread"
    launch_message: str | None = None
    idempotency_key: str | None = None
    redis_client: Any | None = None
    execution_id: str | None = None

    def normalized_feature_id(self) -> str:
        return str(self.feature_id or "").strip()

    def params_dict(self) -> dict[str, Any]:
        return dict(self.params or {})
