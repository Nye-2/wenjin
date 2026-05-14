"""Unified launch path for workspace feature executions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.commands import FeatureLaunchCommand
from src.application.errors import AccessDeniedError, NotFoundError
from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureLaunchResult,
    FeatureTaskSubmission,
)
from src.application.services.feature_launch_context import (
    build_execution_launch_params,
    build_missing_context_advisory,
    extract_feature_params,
    hydrate_missing_context_params_from_resume_message,
    resolve_missing_context_fields,
)
from src.application.services.feature_submission_service import FeatureSubmissionService
from src.application.workspace_resolvers import resolve_workspace_type
from src.compute.session_service import ComputeSessionService
from src.services.execution_service import ExecutionService
from src.workspace_features import get_workspace_feature


def _normalize_str(value: Any) -> str:
    return str(value or "").strip()


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
            existing_execution_id = str(outcome.execution_id or "").strip()
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
                # Return the existing execution_id so the frontend can
                # subscribe to the correct stream.
                execution_id = str(outcome.execution_id or "").strip() or execution_id

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

            merged_params = hydrate_missing_context_params_from_resume_message(
                feature_id=feature.id,
                params={**extract_feature_params(execution.params), **resolved_params},
                launch_source=command.launch_source,
                launch_message=command.launch_message,
            )
            missing_fields = resolve_missing_context_fields(
                feature_id=feature.id,
                params=merged_params,
                launch_source=command.launch_source,
            )

            await self.execution_service.update_execution(
                str(execution.id),
                thread_id=command.thread_id if command.thread_id else execution.thread_id,
                entry_skill_id=command.skill_id if command.skill_id else execution.entry_skill_id,
                params=build_execution_launch_params(
                    feature_id=feature.id,
                    params=merged_params,
                    workspace_id=workspace_id,
                    launch_message=command.launch_message,
                ),
                status="running",
            )

            if missing_fields:
                advisory = build_missing_context_advisory(
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

        # Create ExecutionRecord before dispatch so the gateway
        # can return execution_id to the frontend immediately.
        execution_record = await self.execution_service.create_execution(
            execution_type="feature",
            user_id=self.actor_id,
            workspace_id=workspace_id,
            thread_id=command.thread_id,
            feature_id=feature.id,
            entry_skill_id=command.skill_id,
            workspace_type=workspace_type,
            params=build_execution_launch_params(
                feature_id=feature.id,
                params=resolved_params,
                workspace_id=workspace_id,
                launch_message=command.launch_message,
            ),
        )
        execution_id = execution_record.id
        await self.compute_session_service.ensure_for_execution(
            execution_id=execution_id,
            workspace_id=workspace_id,
            user_id=self.actor_id,
        )

        missing_fields = resolve_missing_context_fields(
            feature_id=feature.id,
            params=resolved_params,
            launch_source=command.launch_source,
        )
        if missing_fields:
            advisory = build_missing_context_advisory(
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
