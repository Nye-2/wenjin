"""Feature execution handler — application-layer orchestration.

Extracts business orchestration from the features router into a dedicated
handler, keeping the router as a thin HTTP adapter.

Responsibilities:
- Workspace ownership verification
- Literature threshold checks (thesis_writing)
- Idempotent task deduplication
- Credit billing with failure compensation
- Task submission and payload construction
"""

import logging
from typing import Any

from fastapi import Depends

from src.academic.services.workspace_service import WorkspaceService
from src.application.errors import (
    AccessDeniedError,
    InternalServiceError,
    NotFoundError,
)
from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureExecutionOutcome,
    FeatureTaskSubmission,
)
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.dependencies import (
    get_credit_service,
    get_literature_service,
    get_task_service,
    get_workspace_service,
)
from src.services.credit_service import CreditService, InsufficientCreditsError
from src.services.literature_service import LiteratureService
from src.task.service import ConcurrencyLimitError, TaskService
from src.workspace_features import get_workspace_feature

logger = logging.getLogger(__name__)

# Recommended minimum literature count for thesis writing
LITERATURE_THRESHOLD = 15

# Idempotency key TTL in seconds (24 hours)
IDEMPOTENCY_KEY_TTL = 86400


def resolve_workspace_type(workspace: Any) -> str:
    """Normalize workspace.type across enum and string shapes."""
    workspace_type = getattr(workspace, "type", None)
    if workspace_type is None:
        return "thesis"
    return workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)


def build_task_payload(
    *,
    workspace: Any,
    workspace_id: str,
    workspace_type: str,
    feature: Any,
    params: dict[str, Any],
    thread_id: str | None,
) -> dict[str, Any]:
    """Build the canonical task payload for workspace feature execution."""
    payload = dict(params)
    payload.update(
        {
            "workspace_id": workspace_id,
            "workspace_type": workspace_type,
            "workspace_name": getattr(workspace, "name", ""),
            "workspace_description": getattr(workspace, "description", ""),
            "workspace_discipline": getattr(workspace, "discipline", ""),
            "workspace_config": getattr(workspace, "config", {}) or {},
            "feature_id": feature.id,
            "feature_name": feature.name,
            "agent": feature.agent,
            "agent_label": feature.agent_label,
            "handler_key": feature.handler_key,
            "thread_id": thread_id,
            "params": params,
        }
    )
    return payload


class FeatureExecutionHandler:
    """Orchestrates feature execution: ownership, billing, submission."""

    def __init__(
        self,
        *,
        user: User,
        workspace_service: WorkspaceService,
        task_service: TaskService,
        literature_service: LiteratureService,
        credit_service: CreditService,
    ) -> None:
        self.user = user
        self.workspace_service = workspace_service
        self.task_service = task_service
        self.literature_service = literature_service
        self.credit_service = credit_service

    async def execute(
        self,
        workspace_id: str,
        feature_id: str,
        params: dict[str, Any] | None = None,
        thread_id: str | None = None,
        *,
        idempotency_key: str | None = None,
        redis_client: Any | None = None,
    ) -> FeatureExecutionOutcome:
        """Execute a workspace feature.

        Args:
            idempotency_key: Optional client-supplied key for request dedup.
            redis_client: Redis client for idempotency lookups.

        Returns a dict matching ExecuteResponse shape:
            task_id, status, feature_id, message, warning, detail
        """
        params = params or {}

        # 0. Idempotency-Key check (before any side effects)
        if idempotency_key and redis_client:
            idem_redis_key = f"idempotency:{self.user.id}:{idempotency_key}"
            cached_task_id = await redis_client.client.get(idem_redis_key)
            if cached_task_id:
                logger.info(
                    "[Features] Idempotency-Key hit: %s → task %s",
                    idempotency_key,
                    cached_task_id,
                )
                return FeatureTaskSubmission(
                    task_id=cached_task_id,
                    feature_id=feature_id,
                    message="请求已处理（幂等重放）",
                    reused_existing_task=True,
                )

        # 1. Verify workspace exists and user owns it
        workspace = await self.workspace_service.get(workspace_id)
        if not workspace:
            raise NotFoundError("Workspace not found")
        if str(workspace.user_id) != str(self.user.id):
            raise AccessDeniedError("Access denied")

        # 2. Resolve workspace type and feature
        workspace_type = resolve_workspace_type(workspace)
        feature = get_workspace_feature(workspace_type, feature_id)
        if not feature:
            raise NotFoundError(
                f"Feature '{feature_id}' not found for workspace type '{workspace_type}'"
            )

        # 3. Literature threshold check (thesis writing only)
        if feature_id == "thesis_writing":
            action = params.get("action", "write_all")
            if action in ("write_chapter", "write_all"):
                lit_stats = await self.literature_service.count_literature(workspace_id)
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

        # 4. Idempotency: reuse existing active task
        action = params.get("action")
        existing_task_id = await self.task_service.find_active_task(
            user_id=str(self.user.id),
            task_type=feature.task_type,
            workspace_id=workspace_id,
            feature_id=feature_id,
            action=str(action) if action is not None else None,
        )
        if existing_task_id:
            logger.info(
                "[Features] Idempotent hit: returning existing task %s for %s/%s",
                existing_task_id,
                workspace_id,
                feature_id,
            )
            return FeatureTaskSubmission(
                task_id=existing_task_id,
                feature_id=feature_id,
                message=f"已有进行中的 {feature.name} 任务",
                reused_existing_task=True,
            )

        # 5. Credit billing
        credit_transaction = None
        try:
            credit_transaction = await self.credit_service.consume_for_feature(
                user_id=str(self.user.id),
                feature_id=feature_id,
                action=str(action) if action is not None else None,
                workspace_id=workspace_id,
                description=f"{feature.name} 执行消耗",
                metadata={
                    "workspace_type": workspace_type,
                    "handler_key": feature.handler_key,
                    "params": params,
                },
            )
        except InsufficientCreditsError as exc:
            return FeatureExecutionAdvisory(
                feature_id=feature_id,
                message=(
                    f"积分不足：当前 {exc.current_balance}，"
                    f"执行 {feature.name} 需要 {exc.required}"
                ),
                code="insufficient_credits",
                context={
                    "current": exc.current_balance,
                    "required": exc.required,
                    "feature_id": feature_id,
                },
            )

        # 6-9. Submit task (with distributed lock if Redis available)
        return await self._submit_with_lock(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            workspace=workspace,
            feature=feature,
            feature_id=feature_id,
            params=params,
            thread_id=thread_id,
            credit_transaction=credit_transaction,
            idempotency_key=idempotency_key,
            redis_client=redis_client,
        )

    async def _submit_with_lock(
        self,
        *,
        workspace_id: str,
        workspace_type: str,
        workspace: Any,
        feature: Any,
        feature_id: str,
        params: dict[str, Any],
        thread_id: str | None,
        credit_transaction: Any | None,
        idempotency_key: str | None,
        redis_client: Any | None,
    ) -> FeatureExecutionOutcome:
        """Submit task, optionally guarded by distributed workspace lock.

        Re-checks for active tasks inside the lock to prevent the race
        condition where two concurrent requests both pass the optimistic
        dedup check (step 4) and both submit tasks.
        """
        action = params.get("action")

        async def _do_submit() -> dict[str, Any]:
            # Re-check for active task inside lock (atomic dedup)
            existing_task_id = await self.task_service.find_active_task(
                user_id=str(self.user.id),
                task_type=feature.task_type,
                workspace_id=workspace_id,
                feature_id=feature_id,
                action=str(action) if action is not None else None,
            )
            if existing_task_id:
                # Refund credit if we already billed
                if credit_transaction is not None:
                    await self.credit_service.refund_failed_task(
                        user_id=str(self.user.id),
                        original_transaction_id=str(credit_transaction.id),
                        reason="分布式锁内发现重复任务退款",
                    )
                return FeatureTaskSubmission(
                    task_id=existing_task_id,
                    feature_id=feature_id,
                    message=f"已有进行中的 {feature.name} 任务",
                    reused_existing_task=True,
                )

            # Build task payload
            task_payload = build_task_payload(
                workspace=workspace,
                workspace_id=workspace_id,
                workspace_type=workspace_type,
                feature=feature,
                params=params,
                thread_id=thread_id,
            )
            if credit_transaction is not None:
                task_payload["credit_transaction_id"] = str(credit_transaction.id)
                task_payload["credit_cost"] = abs(int(credit_transaction.amount))

            # Submit task
            try:
                task_id = await self.task_service.submit_task(
                    user_id=str(self.user.id),
                    task_type=feature.task_type,
                    payload=task_payload,
                )
            except ConcurrencyLimitError as exc:
                logger.warning(
                    "[Features] Concurrency limit for user %s: %s",
                    self.user.id,
                    exc,
                )
                if credit_transaction is not None:
                    await self.credit_service.refund_failed_task(
                        user_id=str(self.user.id),
                        original_transaction_id=str(credit_transaction.id),
                        reason="并发任务上限退款",
                    )
                return FeatureExecutionAdvisory(
                    feature_id=feature_id,
                    message=f"并发任务数已达上限（{exc.limit}），请等待现有任务完成",
                    code="concurrency_limit",
                    context={
                        "current": exc.current,
                        "limit": exc.limit,
                    },
                )
            except Exception as exc:
                logger.exception(
                    "[Features] Failed to queue task for feature %s in workspace %s",
                    feature_id,
                    workspace_id,
                )
                if credit_transaction is not None:
                    await self.credit_service.refund_failed_task(
                        user_id=str(self.user.id),
                        original_transaction_id=str(credit_transaction.id),
                        reason="任务排队失败退款",
                    )
                raise InternalServiceError("Failed to queue feature task") from exc

            # Link credit transaction to task
            if credit_transaction is not None:
                credit_transaction.task_id = task_id
                await self.credit_service.db.commit()

            # Store idempotency key → task_id mapping
            if idempotency_key and redis_client:
                idem_redis_key = f"idempotency:{self.user.id}:{idempotency_key}"
                await redis_client.client.set(
                    idem_redis_key, task_id, nx=True, ex=IDEMPOTENCY_KEY_TTL
                )

            logger.info(
                "[Features] Started %s task %s for workspace %s",
                feature_id,
                task_id,
                workspace_id,
            )

            return FeatureTaskSubmission(
                task_id=task_id,
                feature_id=feature_id,
                message=f"Queued {feature.name}",
            )

        # Try to use distributed lock; fall back to unlocked if Redis unavailable
        if redis_client:
            try:
                async with redis_client.workspace_lock(workspace_id, timeout=30):
                    return await _do_submit()
            except RuntimeError as exc:
                if "Could not acquire lock" in str(exc):
                    logger.warning(
                        "[Features] Could not acquire workspace lock for %s, "
                        "another submission in progress",
                        workspace_id,
                    )
                    # Refund credit since we cannot proceed
                    if credit_transaction is not None:
                        await self.credit_service.refund_failed_task(
                            user_id=str(self.user.id),
                            original_transaction_id=str(credit_transaction.id),
                            reason="工作区锁竞争退款",
                        )
                    return FeatureExecutionAdvisory(
                        feature_id=feature_id,
                        message="该工作区正在处理另一个提交，请稍后重试",
                        code="workspace_locked",
                    )

                logger.warning(
                    "[Features] Workspace lock unavailable for %s, proceeding without lock: %s",
                    workspace_id,
                    exc,
                )
                return await _do_submit()
        else:
            return await _do_submit()


async def get_feature_execution_handler(
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    task_service: TaskService = Depends(get_task_service),
    literature_service: LiteratureService = Depends(get_literature_service),
    credit_service: CreditService = Depends(get_credit_service),
) -> FeatureExecutionHandler:
    """Construct a FeatureExecutionHandler with request-scoped dependencies."""
    return FeatureExecutionHandler(
        user=current_user,
        workspace_service=workspace_service,
        task_service=task_service,
        literature_service=literature_service,
        credit_service=credit_service,
    )
