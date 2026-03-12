"""Runtime registry and helpers for workspace feature execution."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.academic.services import ArtifactService
from src.database import get_db_session
from src.task.progress import ProgressTracker
from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    FeatureArtifactReference,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.registry import WorkspaceFeatureDefinition

FeatureHandler = Callable[
    ["WorkspaceFeatureExecutionContext"],
    Awaitable[WorkspaceFeatureExecutionResult],
]

_HANDLERS: dict[str, FeatureHandler] = {}
_HANDLERS_LOADED = False


def register_feature_handler(*handler_keys: str) -> Callable[[FeatureHandler], FeatureHandler]:
    """Register a concrete handler for one or more workspace feature handler keys."""

    def decorator(handler: FeatureHandler) -> FeatureHandler:
        for handler_key in handler_keys:
            if handler_key in _HANDLERS:
                raise RuntimeError(f"Feature handler already registered: {handler_key}")
            _HANDLERS[handler_key] = handler
        return handler

    return decorator


def _load_handlers() -> None:
    """Import handler modules once so decorator registration can run."""
    global _HANDLERS_LOADED
    if _HANDLERS_LOADED:
        return

    from src.workspace_features import handlers  # noqa: F401

    _HANDLERS_LOADED = True


@dataclass(slots=True)
class WorkspaceFeatureExecutionContext:
    """Convenience wrapper passed to concrete workspace feature handlers."""

    payload: dict[str, Any]
    progress: ProgressTracker
    feature: WorkspaceFeatureDefinition

    @property
    def workspace_id(self) -> str:
        return str(self.payload.get("workspace_id", ""))

    @property
    def workspace_type(self) -> str:
        return str(self.payload.get("workspace_type", self.feature.workspace_type))

    @property
    def workspace_name(self) -> str:
        return str(self.payload.get("workspace_name") or "")

    @property
    def workspace_description(self) -> str:
        return str(self.payload.get("workspace_description") or "")

    @property
    def workspace_discipline(self) -> str:
        return str(self.payload.get("workspace_discipline") or "")

    @property
    def workspace_config(self) -> dict[str, Any]:
        config = self.payload.get("workspace_config")
        return config if isinstance(config, dict) else {}

    @property
    def feature_id(self) -> str:
        return self.feature.id

    @property
    def feature_name(self) -> str:
        return self.feature.name

    @property
    def handler_key(self) -> str:
        return self.feature.handler_key

    @property
    def agent(self) -> str:
        return self.feature.agent

    @property
    def params(self) -> dict[str, Any]:
        params = self.payload.get("params")
        return params if isinstance(params, dict) else {}

    @property
    def thread_id(self) -> str | None:
        thread_id = self.payload.get("thread_id")
        return str(thread_id) if thread_id else None

    def metadata(self, **extra: Any) -> dict[str, Any]:
        """Build consistent progress metadata for feature handlers."""
        metadata = {
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "workspace_type": self.workspace_type,
            "agent": self.agent,
            "handler_key": self.handler_key,
        }
        metadata.update(extra)
        return metadata

    async def update(
        self,
        progress_value: int,
        message: str,
        *,
        current_step: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit normalized progress updates."""
        await self.progress.update(
            progress_value,
            message,
            current_step=current_step,
            metadata=self.metadata(**(metadata or {})),
        )

    async def persist_artifacts(
        self,
        artifacts: list[FeatureArtifactDraft],
    ) -> list[FeatureArtifactReference]:
        """Persist artifacts produced by the handler."""
        if not artifacts:
            return []

        async with get_db_session() as db:
            service = ArtifactService(db)
            persisted: list[FeatureArtifactReference] = []
            for artifact in artifacts:
                record = await service.create(
                    workspace_id=self.workspace_id,
                    type=artifact.type,
                    title=artifact.title,
                    content=artifact.content,
                    created_by_skill=artifact.created_by_skill or self.handler_key,
                    parent_artifact_id=artifact.parent_artifact_id,
                )
                persisted.append(
                    FeatureArtifactReference(
                        id=record.id,
                        type=record.type,
                        title=record.title,
                    )
                )
        return persisted


async def _execute_placeholder(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Default placeholder for features without concrete implementations yet."""
    await context.update(
        10,
        f"Initializing {context.feature_name}",
        current_step="initialize",
    )
    await context.update(
        65,
        f"{context.feature_name} scaffold completed",
        current_step="execute",
    )
    return WorkspaceFeatureExecutionResult(
        message=f"{context.feature_name} has been routed through the unified task pipeline.",
        next_steps=[
            "Connect this feature to a concrete workflow handler.",
            "Persist generated artifacts through the artifact service.",
        ],
    )


async def execute_registered_feature(
    payload: dict[str, Any],
    progress: ProgressTracker,
    feature: WorkspaceFeatureDefinition,
) -> dict[str, Any]:
    """Execute a registered workspace feature handler and normalize the result."""
    _load_handlers()

    context = WorkspaceFeatureExecutionContext(
        payload=payload,
        progress=progress,
        feature=feature,
    )
    handler = _HANDLERS.get(feature.handler_key)
    result = (
        await handler(context)
        if handler is not None
        else await _execute_placeholder(context)
    )
    return result.to_payload(
        feature_id=context.feature_id,
        feature_name=context.feature_name,
        workspace_type=context.workspace_type,
        agent=context.agent,
        handler_key=context.handler_key,
    )
