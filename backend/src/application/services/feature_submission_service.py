"""Feature execution dispatch service — preflight + execution dispatch."""

import logging
from typing import Any

from src.academic.services.workspace_service import WorkspaceService
from src.application.errors import (
    AccessDeniedError,
    InternalServiceError,
    NotFoundError,
    PaymentRequiredError,
)
from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureExecutionOutcome,
    FeatureTaskSubmission,
)
from src.application.workspace_resolvers import resolve_workspace_type
from src.services.credit_service import CreditService
from src.services.execution_service import ExecutionService
from src.services.references import WorkspaceReferenceService
from src.workspace_features import get_workspace_feature

logger = logging.getLogger(__name__)

# Recommended minimum literature count for thesis writing
LITERATURE_THRESHOLD = 15
# Idempotency key TTL in seconds (24 hours)
IDEMPOTENCY_KEY_TTL = 86400


class FeatureSubmissionService:
    """Run feature preflight checks and dispatch canonical executions."""

    def __init__(
        self,
        *,
        actor_id: str,
        workspace_service: WorkspaceService,
        reference_service: WorkspaceReferenceService,
        credit_service: CreditService,
        execution_service: ExecutionService | None = None,
    ) -> None:
        self.actor_id = actor_id
        self.workspace_service = workspace_service
        self.reference_service = reference_service
        self.credit_service = credit_service
        self.execution_service = execution_service

    async def execute(
        self,
        workspace_id: str,
        feature_id: str,
        params: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        redis_client: Any | None = None,
        execution_id: str,
    ) -> FeatureExecutionOutcome:
        """Validate feature launch prerequisites and dispatch execution.

        Args:
            idempotency_key: Optional client-supplied key for request deduplication.
            redis_client: Redis client for optional dedupe / workspace lock.

        Returns:
            A dispatch/advisory result for the ingress layer.
        """
        if not str(execution_id or "").strip():
            raise InternalServiceError("execution_id is required for feature dispatch")
        params = dict(params or {})

        # 1. Verify workspace exists and user owns it
        workspace = await self.workspace_service.get(workspace_id)
        if not workspace:
            raise NotFoundError("Workspace not found")
        if str(workspace.user_id) != self.actor_id:
            raise AccessDeniedError("Access denied")

        # 2. Resolve workspace type and feature
        try:
            workspace_type = resolve_workspace_type(workspace)
        except ValueError as exc:
            raise InternalServiceError(str(exc)) from exc
        feature = get_workspace_feature(workspace_type, feature_id)
        if not feature:
            raise NotFoundError(
                f"Feature '{feature_id}' not found for workspace type '{workspace_type}'"
            )

        # 3. Literature threshold check (thesis writing only)
        action = params.get("action")
        if feature_id == "thesis_writing":
            normalized_action = str(action or "write_all").strip().lower() or "write_all"
            params["action"] = normalized_action
            action = normalized_action
            if action in ("write_chapter", "write_all"):
                lit_stats = await self.reference_service.count_references(workspace_id)
                if lit_stats["total"] < LITERATURE_THRESHOLD:
                    return FeatureExecutionAdvisory(
                        feature_id=feature_id,
                        message="文献数量不足，建议先补充文献",
                        code="literature_insufficient",
                        context={
                            "current": lit_stats["total"],
                            "recommended": LITERATURE_THRESHOLD,
                        },
                    )

        allowed = await self.credit_service.can_start_feature_task(self.actor_id)
        if not allowed:
            policy = self.credit_service.get_feature_billing_policy()
            raise PaymentRequiredError(
                f"Compute feature 免费额度已用尽。当前策略为前 {policy.free_tokens} tokens 免费，"
                "后续按 token 扣积分，请先补充积分。"
            )

        # 4. Idempotency: reuse existing execution when the caller repeats the request.
        if idempotency_key and redis_client:
            idem_redis_key = f"idempotency:{self.actor_id}:{idempotency_key}"
            cached_execution_id = await redis_client.client.get(idem_redis_key)
            if cached_execution_id:
                logger.info(
                    "[Features] Idempotency-Key hit: %s → execution %s",
                    idempotency_key,
                    cached_execution_id,
                )
                return FeatureTaskSubmission(
                    task_id=str(cached_execution_id),
                    feature_id=feature_id,
                    message="请求已处理（幂等重放）",
                    reused_existing_task=True,
                    execution_id=str(cached_execution_id),
                )

        # 5. Dispatch execution (with distributed lock if Redis available).
        return await self._dispatch_with_lock(
            workspace_id=workspace_id,
            feature=feature,
            feature_id=feature_id,
            idempotency_key=idempotency_key,
            redis_client=redis_client,
            execution_id=execution_id,
        )

    async def _dispatch_with_lock(
        self,
        *,
        workspace_id: str,
        feature: Any,
        feature_id: str,
        idempotency_key: str | None,
        redis_client: Any | None,
        execution_id: str,
    ) -> FeatureExecutionOutcome:
        """Dispatch execution, optionally guarded by distributed workspace lock."""

        async def _do_dispatch() -> FeatureExecutionOutcome:
            try:
                from src.task.tasks.execution import execute_execution

                worker = execute_execution.apply_async(
                    args=[str(execution_id)],
                    queue="long_running",
                )
            except Exception as exc:
                logger.exception(
                    "[Features] Failed to dispatch execution for feature %s in workspace %s",
                    feature_id,
                    workspace_id,
                )
                raise InternalServiceError("Failed to dispatch feature execution") from exc

            worker_task_id = str(getattr(worker, "id", "") or execution_id)
            if self.execution_service is not None:
                await self.execution_service.update_execution(
                    execution_id,
                    dispatch_mode="celery_worker",
                    worker_task_id=worker_task_id,
                )
            if idempotency_key and redis_client:
                idem_redis_key = f"idempotency:{self.actor_id}:{idempotency_key}"
                await redis_client.client.set(
                    idem_redis_key, execution_id, nx=True, ex=IDEMPOTENCY_KEY_TTL
                )

            logger.info(
                "[Features] Dispatched execution %s for feature %s in workspace %s",
                execution_id,
                feature_id,
                workspace_id,
            )

            return FeatureTaskSubmission(
                task_id=worker_task_id,
                feature_id=feature_id,
                message=f"Dispatched {feature.name}",
                execution_id=str(execution_id),
            )

        # Try to use distributed lock; fall back to unlocked if Redis unavailable
        if redis_client:
            try:
                async with redis_client.workspace_lock(workspace_id, timeout=30):
                    return await _do_dispatch()
            except RuntimeError as exc:
                if "Could not acquire lock" in str(exc):
                    logger.warning(
                        "[Features] Could not acquire workspace lock for %s, "
                        "another execution dispatch in progress",
                        workspace_id,
                    )
                    return FeatureExecutionAdvisory(
                        feature_id=feature_id,
                        message="该工作区正在处理另一个执行派发，请稍后重试",
                        code="workspace_locked",
                    )

                logger.warning(
                    "[Features] Workspace lock unavailable for %s, proceeding without lock: %s",
                    workspace_id,
                    exc,
                )
                return await _do_dispatch()
        else:
            return await _do_dispatch()
