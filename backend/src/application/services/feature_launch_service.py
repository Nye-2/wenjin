"""Unified launch path for workspace feature executions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.commands import FeatureLaunchCommand
from src.application.errors import AccessDeniedError, NotFoundError
from src.application.intents.launch_text import (
    is_generic_feature_launch_text,
    normalize_inline_text,
)
from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureLaunchResult,
    FeatureTaskSubmission,
)
from src.application.services.feature_submission_service import FeatureSubmissionService
from src.application.workspace_resolvers import resolve_workspace_type
from src.compute.session_service import ComputeSessionService
from src.services.execution_service import ExecutionService
from src.workspace_features import get_workspace_feature

_THREAD_ENTRY_SOURCES = {"thread", "tool", "automation"}

# feature_id -> requirement groups (each group means "at least one must be present")
_FEATURE_CONTEXT_REQUIREMENTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "deep_research": (("topic", "query"),),
    "literature_search": (("query", "topic", "keywords"),),
    "background_research": (("keywords", "topic", "query"),),
    "prior_art_search": (("keywords", "query", "topic"),),
    "opening_research": (("topic", "query"),),
}
_FEATURE_CONTEXT_FIELD_LABELS: dict[str, str] = {
    "topic": "研究主题",
    "query": "检索问题",
    "keywords": "关键词",
}


def _normalize_str(value: Any) -> str:
    return str(value or "").strip()


def _is_value_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_is_value_present(item) for item in value)
    if isinstance(value, Mapping):
        return bool(value)
    return value is not None


def _resolve_missing_context_fields(
    *,
    feature_id: str,
    params: Mapping[str, Any],
    launch_source: str,
) -> list[str]:
    if launch_source not in _THREAD_ENTRY_SOURCES:
        return []
    requirements = _FEATURE_CONTEXT_REQUIREMENTS.get(feature_id)
    if not requirements:
        return []

    missing: list[str] = []
    for group in requirements:
        if any(_is_value_present(params.get(field)) for field in group):
            continue
        missing.append(group[0])
    return missing


def _build_missing_context_advisory(
    *,
    feature_id: str,
    missing_fields: list[str],
) -> FeatureExecutionAdvisory:
    missing_fields_str = "、".join(
        _FEATURE_CONTEXT_FIELD_LABELS.get(field, field)
        for field in missing_fields
    )
    prompt = (
        f"继续执行「{feature_id}」前，还需要你补充：{missing_fields_str}。"
        " 请直接回复补充信息，我会在当前执行会话继续。"
    )
    return FeatureExecutionAdvisory(
        feature_id=feature_id,
        code="missing_params",
        message=prompt,
        context={
            "missing_fields": list(missing_fields),
            "prompt": prompt,
        },
    )


def _resolve_resume_context_seed(
    *,
    params: Mapping[str, Any],
    launch_message: str | None,
) -> str:
    """Pick the best user-provided text snippet for missing context hydration."""
    candidates: list[tuple[Any, bool]] = [
        (launch_message, False),
        (params.get("__thread_context_focus"), False),
        (params.get("__thread_context_digest"), True),
    ]
    for candidate, is_digest in candidates:
        normalized = normalize_inline_text(candidate)
        if not normalized or is_generic_feature_launch_text(normalized):
            continue
        if is_digest:
            for line in reversed(str(candidate).splitlines()):
                line_text = normalize_inline_text(line)
                if line_text.startswith("用户:"):
                    recovered = normalize_inline_text(line_text.removeprefix("用户:"))
                    if recovered and not is_generic_feature_launch_text(recovered):
                        normalized = recovered
                        break
        if len(normalized) > 280:
            return normalized[:279].rstrip() + "…"
        return normalized
    return ""


def _hydrate_missing_context_params_from_resume_message(
    *,
    feature_id: str,
    params: Mapping[str, Any],
    launch_source: str,
    launch_message: str | None,
) -> dict[str, Any]:
    """Backfill required fields from resume user input to avoid missing-param loops."""
    hydrated = dict(params)
    if launch_source not in _THREAD_ENTRY_SOURCES:
        return hydrated
    requirements = _FEATURE_CONTEXT_REQUIREMENTS.get(feature_id)
    if not requirements:
        return hydrated

    seed_text = _resolve_resume_context_seed(
        params=hydrated,
        launch_message=launch_message,
    )
    if not seed_text:
        return hydrated

    for group in requirements:
        if any(_is_value_present(hydrated.get(field)) for field in group):
            continue
        hydrated[group[0]] = seed_text
    return hydrated


class FeatureIngressService:
    """Canonical ingress for workspace feature launch/resume."""

    def __init__(
        self,
        *,
        actor_id: str,
        feature_submission_service: FeatureSubmissionService,
        execution_service: ExecutionService,
        compute_session_service: ComputeSessionService,
        workspace_service: Any,
    ) -> None:
        self.actor_id = actor_id
        self.feature_submission_service = feature_submission_service
        self.execution_service = execution_service
        self.compute_session_service = compute_session_service
        self.workspace_service = workspace_service

    async def _load_workspace_and_feature(
        self,
        *,
        workspace_id: str,
        feature_id: str,
    ) -> tuple[Any, str, Any]:
        workspace = await self.workspace_service.get(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        if str(workspace.user_id) != self.actor_id:
            raise AccessDeniedError("Access denied")

        workspace_type = resolve_workspace_type(workspace)
        feature = get_workspace_feature(workspace_type, feature_id)
        if feature is None:
            raise NotFoundError(
                f"Feature '{feature_id}' not found for workspace type '{workspace_type}'"
            )
        return workspace, workspace_type, feature

    async def _persist_missing_context(
        self,
        *,
        execution_id: str | None,
        params: dict[str, Any],
        advisory: FeatureExecutionAdvisory,
        thread_id: str | None,
        skill_id: str | None,
    ) -> None:
        if execution_id:
            await self.execution_service.update_execution(
                execution_id,
                status="awaiting_user_input",
                thread_id=thread_id,
                entry_skill_id=skill_id,
                params=params,
                advisory_code=advisory.code,
                result_summary=advisory.message,
                last_error=None,
                next_actions=[
                    {
                        "kind": "user_input_required",
                        "feature_id": advisory.feature_id,
                        "missing_fields": advisory.context.get("missing_fields")
                        if isinstance(advisory.context, dict)
                        else [],
                        "prompt": advisory.context.get("prompt")
                        if isinstance(advisory.context, dict)
                        else advisory.message,
                    }
                ],
            )

    async def _finalize_submission(
        self,
        *,
        outcome: FeatureTaskSubmission,
        allow_repoint_to_existing_execution: bool,
        workspace_id: str,
        user_id: str,
        execution_id: str | None,
    ) -> str:
        if outcome.reused_existing_task:
            existing_task = await self.feature_submission_service.task_service.get_task_status(
                outcome.task_id,
                self.actor_id,
            )
            existing_execution_id = (
                str(existing_task.get("execution_id") or "").strip()
                if isinstance(existing_task, dict)
                else ""
            )
            if (
                allow_repoint_to_existing_execution
                and existing_execution_id
                and existing_execution_id != str(execution_id or "")
            ):
                await self.compute_session_service.ensure_for_execution(
                    execution_id=existing_execution_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
                return existing_execution_id

        if execution_id:
            await self.execution_service.update_execution(
                execution_id,
                status="pending",
                result_summary=outcome.message,
                next_actions=[],
                advisory_code=None,
                last_error=None,
            )
        return str(execution_id or "")

    async def _resolve_existing_execution_id(self, task_id: str) -> str | None:
        """Get execution_id from an existing task's payload."""
        try:
            from src.task.store import TaskStore
            store = TaskStore(None, self.execution_session_service.db)
            record = await store.get_task_record(task_id)
            if record and isinstance(record.payload, dict):
                return str(record.payload.get("execution_id") or "").strip() or None
        except Exception:
            pass
        return None

    async def _handle_execution_outcome(
        self,
        *,
        outcome: FeatureTaskSubmission | FeatureExecutionAdvisory,
        params: dict[str, Any],
        thread_id: str | None,
        skill_id: str | None,
        allow_repoint_to_existing_execution: bool,
        workspace_id: str,
        user_id: str,
        execution_id: str | None = None,
    ) -> FeatureLaunchResult:
        if isinstance(outcome, FeatureTaskSubmission):
            if outcome.reused_existing_task and execution_id:
                # Cancel the pre-created ExecutionRecord; it won't be started.
                try:
                    await self.execution_service.cancel_execution(execution_id)
                except Exception:
                    pass
                # Return the existing task's execution_id so the frontend
                # can subscribe to the correct stream.
                execution_id = await self._resolve_existing_execution_id(outcome.task_id)

            execution_id = await self._finalize_submission(
                outcome=outcome,
                allow_repoint_to_existing_execution=allow_repoint_to_existing_execution,
                workspace_id=workspace_id,
                user_id=user_id,
                execution_id=execution_id,
            )
            return FeatureLaunchResult(
                execution_id=execution_id,
                outcome=outcome,
            )

        # Task was not submitted (advisory).  Complete the ExecutionRecord
        # so it does not stay in ``pending`` forever.
        if execution_id:
            try:
                await self.execution_service.complete_execution(
                    execution_id,
                    status="failed",
                    error=f"Launch advisory: {outcome.code} — {outcome.message}",
                )
            except Exception:
                pass

        if outcome.code == "missing_params":
            await self._persist_missing_context(
                execution_id=execution_id,
                params=params,
                advisory=outcome,
                thread_id=thread_id,
                skill_id=skill_id,
            )
            return FeatureLaunchResult(
                execution_id=str(execution_id or ""),
                outcome=outcome,
            )

        if execution_id:
            await self.execution_service.update_execution(
                execution_id,
                status="awaiting_user_input",
                advisory_code=outcome.code,
                result_summary=outcome.message,
                last_error=outcome.message,
            )
        return FeatureLaunchResult(
            execution_id=str(execution_id or ""),
            outcome=outcome,
        )

    async def launch(
        self,
        command: FeatureLaunchCommand,
    ) -> FeatureLaunchResult:
        workspace_id = command.workspace_id
        resolved_feature_id = command.normalized_feature_id()
        resolved_params = command.params_dict()

        if command.execution_id:
            execution = await self.execution_service.get_by_id(command.execution_id)
            if execution is None:
                raise NotFoundError("Execution not found")
            if str(execution.user_id) != self.actor_id:
                raise AccessDeniedError("Access denied")
            if str(execution.workspace_id) != workspace_id:
                raise AccessDeniedError("Access denied")

            if command.thread_id and execution.thread_id and str(execution.thread_id) != str(command.thread_id):
                raise AccessDeniedError("Execution does not belong to this thread")
            await self.compute_session_service.ensure_for_execution(
                execution_id=str(execution.id),
                workspace_id=workspace_id,
                user_id=self.actor_id,
            )

            if not resolved_feature_id:
                resolved_feature_id = str(execution.feature_id)
            elif resolved_feature_id != str(execution.feature_id):
                raise NotFoundError(
                    "Execution feature does not match requested feature"
                )

            _, _, feature = await self._load_workspace_and_feature(
                workspace_id=workspace_id,
                feature_id=resolved_feature_id,
            )

            merged_params = _hydrate_missing_context_params_from_resume_message(
                feature_id=feature.id,
                params={**dict(execution.params or {}), **resolved_params},
                launch_source=command.launch_source,
                launch_message=command.launch_message,
            )
            missing_fields = _resolve_missing_context_fields(
                feature_id=feature.id,
                params=merged_params,
                launch_source=command.launch_source,
            )

            await self.execution_service.update_execution(
                str(execution.id),
                thread_id=command.thread_id if command.thread_id else execution.thread_id,
                entry_skill_id=command.skill_id if command.skill_id else execution.entry_skill_id,
                params=merged_params,
                status="running",
            )

            if missing_fields:
                advisory = _build_missing_context_advisory(
                    feature_id=feature.id,
                    missing_fields=missing_fields,
                )
                await self._persist_missing_context(
                    execution_id=str(execution.id),
                    params=merged_params,
                    advisory=advisory,
                    thread_id=command.thread_id if command.thread_id else execution.thread_id,
                    skill_id=command.skill_id if command.skill_id else execution.entry_skill_id,
                )
                return FeatureLaunchResult(
                    execution_id=str(execution.id),
                    outcome=advisory,
                )

            execution_id = execution.id

            try:
                outcome = await self.feature_submission_service.execute(
                    workspace_id,
                    feature.id,
                    merged_params,
                    command.thread_id or execution.thread_id,
                    command.skill_id or execution.entry_skill_id,
                    idempotency_key=command.idempotency_key,
                    redis_client=command.redis_client,
                    execution_id=execution_id,
                )
            except Exception as exc:
                await self.execution_service.update_execution(
                    execution_id,
                    status="failed",
                    last_error=str(exc),
                    result_summary=str(exc),
                )
                raise

            return await self._handle_execution_outcome(
                outcome=outcome,
                params=merged_params,
                thread_id=command.thread_id if command.thread_id else execution.thread_id,
                skill_id=command.skill_id if command.skill_id else execution.entry_skill_id,
                allow_repoint_to_existing_execution=False,
                workspace_id=workspace_id,
                user_id=self.actor_id,
                execution_id=execution_id,
            )

        if not resolved_feature_id:
            raise NotFoundError("feature_id is required when execution_id is not provided")

        _, workspace_type, feature = await self._load_workspace_and_feature(
            workspace_id=workspace_id,
            feature_id=resolved_feature_id,
        )

        # Create ExecutionRecord before task submission so the gateway
        # can return execution_id to the frontend immediately.
        execution_record = await self.execution_service.create_execution(
            execution_type="feature",
            user_id=self.actor_id,
            workspace_id=workspace_id,
            thread_id=command.thread_id,
            feature_id=feature.id,
            entry_skill_id=command.skill_id,
            workspace_type=workspace_type,
            params=dict(resolved_params),
        )
        execution_id = execution_record.id
        await self.compute_session_service.ensure_for_execution(
            execution_id=execution_id,
            workspace_id=workspace_id,
            user_id=self.actor_id,
        )

        missing_fields = _resolve_missing_context_fields(
            feature_id=feature.id,
            params=resolved_params,
            launch_source=command.launch_source,
        )
        if missing_fields:
            advisory = _build_missing_context_advisory(
                feature_id=feature.id,
                missing_fields=missing_fields,
            )
            await self._persist_missing_context(
                execution_id=execution_id,
                params=resolved_params,
                advisory=advisory,
                thread_id=command.thread_id,
                skill_id=command.skill_id,
            )
            return FeatureLaunchResult(
                execution_id=execution_id,
                outcome=advisory,
            )

        try:
            outcome = await self.feature_submission_service.execute(
                workspace_id,
                feature.id,
                resolved_params,
                command.thread_id,
                command.skill_id,
                idempotency_key=command.idempotency_key,
                redis_client=command.redis_client,
                execution_id=execution_id,
            )
        except Exception as exc:
            await self.execution_service.update_execution(
                execution_id,
                status="failed",
                last_error=str(exc),
                result_summary=str(exc),
            )
            raise

        return await self._handle_execution_outcome(
            outcome=outcome,
            params=resolved_params,
            thread_id=command.thread_id,
            skill_id=command.skill_id,
            allow_repoint_to_existing_execution=True,
            workspace_id=workspace_id,
            user_id=self.actor_id,
            execution_id=execution_id,
        )
