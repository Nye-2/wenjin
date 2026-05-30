"""Credit service for balance management and credit ledger operations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditRefundPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.billing_policy import (
    OperationBillingPolicy,
    TokenBillingPolicy,
    calculate_token_billing_charge,
    get_feature_token_billing_policy,
    get_sandbox_operation_billing_policy,
    get_thread_token_billing_policy,
)
from src.services.billing_policy import (
    get_public_workflow_costs as get_public_billing_workflow_costs,
)
from src.services.billing_policy import (
    get_workflow_costs as get_billing_workflow_costs,
)
from src.services.thread_billing import (
    TokenUsage,
    normalize_token_usage,
)

REGISTRATION_BONUS = 100


class CreditTransactionType(StrEnum):
    ADMIN_GRANT = "admin_grant"
    ADMIN_DEDUCT = "admin_deduct"
    WORKFLOW_CONSUME = "workflow_consume"
    THREAD_TOKEN_CONSUME = "thread_token_consume"
    REGISTRATION_BONUS = "registration_bonus"
    REFUND = "refund"
    REFERRAL_BONUS = "referral_bonus"
    REDEEM_CODE = "redeem_code"


@dataclass(slots=True)
class ThreadCreditConsumption:
    """Result of settling one thread turn against the credit ledger."""

    token_usage: dict[str, int]
    model_name: str | None
    free_tokens_applied: int
    billable_tokens: int
    credits_charged: int
    historical_tokens_before: int
    historical_tokens_after: int
    transaction_id: str | None
    balance_after: int | None
    charged: bool

    def as_metadata(self) -> dict[str, Any]:
        """Return persisted billing metadata for thread messages."""
        return {
            "type": "thread_token_billing",
            "token_usage": dict(self.token_usage),
            "model_name": self.model_name,
            "free_tokens_applied": self.free_tokens_applied,
            "billable_tokens": self.billable_tokens,
            "credits_charged": self.credits_charged,
            "historical_tokens_before": self.historical_tokens_before,
            "historical_tokens_after": self.historical_tokens_after,
            "transaction_id": self.transaction_id,
            "balance_after": self.balance_after,
            "charged": self.charged,
        }


@dataclass(slots=True)
class FeatureCreditConsumption:
    """Result of settling a completed feature task against token usage."""

    token_usage: dict[str, int]
    free_tokens_applied: int
    billable_tokens: int
    credits_charged: int
    historical_tokens_before: int
    historical_tokens_after: int
    transaction_id: str | None
    balance_after: int | None
    charged: bool

    def as_metadata(self) -> dict[str, Any]:
        """Return persisted billing metadata for task results."""
        return {
            "type": "feature_token_billing",
            "token_usage": dict(self.token_usage),
            "free_tokens_applied": self.free_tokens_applied,
            "billable_tokens": self.billable_tokens,
            "credits_charged": self.credits_charged,
            "historical_tokens_before": self.historical_tokens_before,
            "historical_tokens_after": self.historical_tokens_after,
            "transaction_id": self.transaction_id,
            "balance_after": self.balance_after,
            "charged": self.charged,
        }


@dataclass(slots=True)
class SandboxOperationCreditConsumption:
    """Result of settling one fixed-credit sandbox operation."""

    operation: str
    credits_charged: int
    transaction_id: str | None
    balance_after: int | None
    charged: bool

    def as_metadata(self) -> dict[str, Any]:
        """Return persisted billing metadata for sandbox tool output."""
        return {
            "type": "sandbox_operation_billing",
            "operation": self.operation,
            "credits_charged": self.credits_charged,
            "transaction_id": self.transaction_id,
            "balance_after": self.balance_after,
            "charged": self.charged,
        }


class CreditService:
    """Credit accounting service."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self.db = db
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    @staticmethod
    def get_thread_billing_policy() -> TokenBillingPolicy:
        """Return the configured thread token billing policy."""
        return get_thread_token_billing_policy()

    @staticmethod
    def get_feature_billing_policy() -> TokenBillingPolicy:
        """Return the configured workspace feature token billing policy."""
        return get_feature_token_billing_policy()

    @staticmethod
    def get_sandbox_billing_policy() -> OperationBillingPolicy:
        """Return the configured sandbox operation billing policy."""
        return get_sandbox_operation_billing_policy()

    @classmethod
    def get_workflow_costs(cls) -> dict[str, Any]:
        """Expose internal workflow and thread billing configuration."""
        return get_billing_workflow_costs()

    @classmethod
    def get_public_workflow_costs(cls) -> dict[str, Any]:
        """Expose user-facing credit costs without internal token policy details."""
        return get_public_billing_workflow_costs()

    async def get_balance(self, user_id: str) -> int:
        """Get user current credit balance."""
        async with self._client() as client:
            balance = await client.get_credit_balance(user_id)
        if balance is None:
            raise ValueError("User not found")
        return int(balance)

    async def get_credit_summary(self, user_id: str) -> dict[str, int]:
        """Get user credit summary."""
        async with self._client() as client:
            summary = await client.get_credit_summary(user_id)
        if summary is None:
            raise ValueError("User not found")
        return summary.model_dump()

    async def get_history(
        self,
        *,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        transaction_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated credit history for a single user."""
        tx_type = self._parse_transaction_type(transaction_type)
        async with self._client() as client:
            history = await client.get_credit_history(
                user_id=user_id,
                transaction_type=tx_type,
                limit=limit,
                offset=offset,
            )
        return [self._to_public_dict(tx) for tx in history.transactions], int(history.total)

    async def get_all_history(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        user_id: str | None = None,
        transaction_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated credit history across users (admin view)."""
        tx_type = self._parse_transaction_type(transaction_type)
        async with self._client() as client:
            history = await client.get_credit_history(
                user_id=user_id,
                transaction_type=tx_type,
                limit=limit,
                offset=offset,
            )
        return [self._to_dict(tx) for tx in history.transactions], int(history.total)

    async def get_consumed_thread_tokens(self, user_id: str) -> int:
        """Return successfully settled historical thread tokens for a user."""
        async with self._client() as client:
            return await client.get_credit_consumed_tokens(
                user_id=user_id,
                consume_type=CreditTransactionType.THREAD_TOKEN_CONSUME.value,
            )

    async def get_consumed_feature_tokens(self, user_id: str) -> int:
        """Return successfully settled historical feature-task tokens for a user."""
        async with self._client() as client:
            return await client.get_credit_consumed_tokens(
                user_id=user_id,
                consume_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                metadata_type="feature_token_billing",
            )

    async def can_start_thread_turn(self, user_id: str) -> bool:
        """Return whether the user can start a billable thread turn.

        Uses ``SELECT ... FOR UPDATE`` on the user row so that concurrent
        requests serialise on the same balance, preventing two callers from
        both passing the check before either deducts credits.
        """
        policy = self.get_thread_billing_policy()
        if not policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_thread_tokens(user_id)
        if consumed_tokens < policy.free_tokens:
            return True

        return await self.get_balance(user_id) > 0

    async def can_start_feature_task(self, user_id: str) -> bool:
        """Return whether the user can enqueue a billable feature task.

        Feature tasks are settled from measured token usage after successful
        execution, so this is an admission-control gate rather than a
        reservation. It prevents zero/negative-balance users from starting new
        Compute work once the configured feature free-token quota is exhausted.
        """
        policy = self.get_feature_billing_policy()
        if not policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_feature_tokens(user_id)
        if consumed_tokens < policy.free_tokens:
            return True

        return await self.get_balance(user_id) > 0

    async def can_start_sandbox_operation(self, user_id: str, operation: str) -> bool:
        """Return whether the user can start a fixed-credit sandbox operation."""
        policy = self.get_sandbox_billing_policy()
        credits_to_charge = self._sandbox_operation_credits(policy, operation)
        if not policy.enabled or credits_to_charge <= 0:
            return True
        return await self.get_balance(user_id) > 0

    @staticmethod
    def _normalize_usage_dict(token_usage: TokenUsage | dict[str, int]) -> dict[str, int]:
        if isinstance(token_usage, TokenUsage):
            return token_usage.as_dict()
        usage = normalize_token_usage(token_usage)
        if usage is not None:
            return usage.as_dict()
        input_tokens = max(int(token_usage.get("input_tokens", 0) or 0), 0)
        output_tokens = max(int(token_usage.get("output_tokens", 0) or 0), 0)
        total_tokens = max(int(token_usage.get("total_tokens", 0) or 0), 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _transaction_metadata(tx: Any) -> dict[str, Any]:
        metadata = getattr(tx, "metadata", None)
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _metadata_int(metadata: dict[str, Any], key: str, default: int) -> int:
        try:
            return int(metadata.get(key, default) or 0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _transaction_charge(tx: Any, default: int) -> int:
        try:
            return abs(int(getattr(tx, "amount", default) or 0))
        except (TypeError, ValueError):
            return default

    async def consume_for_thread_usage(
        self,
        *,
        user_id: str,
        token_usage: TokenUsage | dict[str, int],
        model_name: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ThreadCreditConsumption:
        """Consume credits for a completed thread turn based on token usage."""
        policy = self.get_thread_billing_policy()
        normalized_usage = self._normalize_usage_dict(token_usage)
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_thread_tokens(user_id)
        charge = calculate_token_billing_charge(
            policy=policy,
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        historical_tokens_after = charge.historical_tokens_after

        if not policy.enabled or total_tokens <= 0:
            return ThreadCreditConsumption(
                token_usage=normalized_usage,
                model_name=model_name,
                free_tokens_applied=0,
                billable_tokens=0,
                credits_charged=0,
                historical_tokens_before=historical_tokens_before,
                historical_tokens_after=historical_tokens_after,
                transaction_id=None,
                balance_after=None,
                charged=False,
            )

        credits_to_charge = charge.credits_to_charge

        tx_metadata = {
            "type": "thread_token_billing",
            "token_usage": normalized_usage,
            "thread_id": thread_id,
            "policy": policy.as_dict(),
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": charge.free_tokens_applied,
            "billable_tokens": charge.billable_tokens,
            "credits_charged": credits_to_charge,
            "model_name": model_name,
        }
        if metadata:
            tx_metadata.update(metadata)

        async with self._client() as client:
            tx, balance_before = await client.record_credit_consumption(
                CreditConsumptionCreatePayload(
                    user_id=user_id,
                    transaction_type=CreditTransactionType.THREAD_TOKEN_CONSUME.value,
                    amount=credits_to_charge,
                    description=description or self._build_thread_description(
                        total_tokens=total_tokens,
                        credits_charged=credits_to_charge,
                        free_tokens_applied=charge.free_tokens_applied,
                    ),
                    feature_id="thread",
                    workspace_id=workspace_id,
                    task_id=None,
                    metadata=tx_metadata,
                )
            )
        if tx is None:
            raise ValueError("Credit transaction was not recorded")
        recorded_metadata = self._transaction_metadata(tx)
        recorded_usage = self._normalize_usage_dict(
            recorded_metadata.get("token_usage", normalized_usage)
        )
        recorded_charge = self._transaction_charge(tx, credits_to_charge)
        return ThreadCreditConsumption(
            token_usage=recorded_usage,
            model_name=model_name,
            free_tokens_applied=self._metadata_int(
                recorded_metadata,
                "free_tokens_applied",
                charge.free_tokens_applied,
            ),
            billable_tokens=self._metadata_int(
                recorded_metadata,
                "billable_tokens",
                charge.billable_tokens,
            ),
            credits_charged=recorded_charge,
            historical_tokens_before=self._metadata_int(
                recorded_metadata,
                "historical_tokens_before",
                historical_tokens_before,
            ),
            historical_tokens_after=self._metadata_int(
                recorded_metadata,
                "historical_tokens_after",
                historical_tokens_after,
            ),
            transaction_id=str(tx.id),
            balance_after=int(tx.balance_after),
            charged=recorded_charge > 0,
        )

    async def consume_for_feature_usage(
        self,
        *,
        user_id: str,
        feature_id: str,
        token_usage: TokenUsage | dict[str, int],
        workspace_id: str | None = None,
        task_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureCreditConsumption:
        """Consume credits for a completed feature task based on token usage."""
        policy = self.get_feature_billing_policy()
        normalized_usage = self._normalize_usage_dict(token_usage)
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_feature_tokens(user_id)
        charge = calculate_token_billing_charge(
            policy=policy,
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        historical_tokens_after = charge.historical_tokens_after

        if not policy.enabled or total_tokens <= 0:
            return FeatureCreditConsumption(
                token_usage=normalized_usage,
                free_tokens_applied=0,
                billable_tokens=0,
                credits_charged=0,
                historical_tokens_before=historical_tokens_before,
                historical_tokens_after=historical_tokens_after,
                transaction_id=None,
                balance_after=None,
                charged=False,
            )

        credits_to_charge = charge.credits_to_charge

        tx_metadata = {
            "type": "feature_token_billing",
            "token_usage": normalized_usage,
            "policy": policy.as_dict(),
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": charge.free_tokens_applied,
            "billable_tokens": charge.billable_tokens,
            "credits_charged": credits_to_charge,
        }
        if metadata:
            tx_metadata.update(metadata)
        if task_id:
            tx_metadata["idempotency_key"] = f"feature_token_billing:{task_id}"

        async with self._client() as client:
            tx, balance_before = await client.record_credit_consumption(
                CreditConsumptionCreatePayload(
                    user_id=user_id,
                    transaction_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                    amount=credits_to_charge,
                    description=description or self._build_feature_token_description(
                        feature_id=feature_id,
                        total_tokens=total_tokens,
                        credits_charged=credits_to_charge,
                        free_tokens_applied=charge.free_tokens_applied,
                    ),
                    feature_id=feature_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    metadata=tx_metadata,
                )
            )
        if tx is None:
            raise ValueError("Credit transaction was not recorded")
        recorded_metadata = self._transaction_metadata(tx)
        recorded_usage = self._normalize_usage_dict(
            recorded_metadata.get("token_usage", normalized_usage)
        )
        recorded_charge = self._transaction_charge(tx, credits_to_charge)
        return FeatureCreditConsumption(
            token_usage=recorded_usage,
            free_tokens_applied=self._metadata_int(
                recorded_metadata,
                "free_tokens_applied",
                charge.free_tokens_applied,
            ),
            billable_tokens=self._metadata_int(
                recorded_metadata,
                "billable_tokens",
                charge.billable_tokens,
            ),
            credits_charged=recorded_charge,
            historical_tokens_before=self._metadata_int(
                recorded_metadata,
                "historical_tokens_before",
                historical_tokens_before,
            ),
            historical_tokens_after=self._metadata_int(
                recorded_metadata,
                "historical_tokens_after",
                historical_tokens_after,
            ),
            transaction_id=str(tx.id),
            balance_after=int(tx.balance_after),
            charged=recorded_charge > 0,
        )

    async def consume_for_sandbox_operation(
        self,
        *,
        user_id: str,
        operation: str,
        workspace_id: str | None = None,
        task_id: str | None = None,
        node_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SandboxOperationCreditConsumption:
        """Consume credits for a fixed-cost sandbox operation before execution."""
        normalized_operation = self._normalize_sandbox_operation(operation)
        policy = self.get_sandbox_billing_policy()
        credits_to_charge = self._sandbox_operation_credits(policy, normalized_operation)
        if not policy.enabled or credits_to_charge <= 0:
            return SandboxOperationCreditConsumption(
                operation=normalized_operation,
                credits_charged=0,
                transaction_id=None,
                balance_after=None,
                charged=False,
            )

        tx_metadata: dict[str, Any] = {
            "type": "sandbox_operation_billing",
            "operation": normalized_operation,
            "credits_charged": credits_to_charge,
            "policy": policy.as_dict(),
        }
        if node_id:
            tx_metadata["node_id"] = node_id
        if metadata:
            tx_metadata.update(metadata)
        if task_id and node_id:
            tx_metadata["idempotency_key"] = (
                f"sandbox_operation_billing:{task_id}:{node_id}:{normalized_operation}"
            )
        elif task_id:
            tx_metadata["idempotency_key"] = (
                f"sandbox_operation_billing:{task_id}:{normalized_operation}"
            )

        async with self._client() as client:
            tx, balance_before = await client.record_credit_consumption(
                CreditConsumptionCreatePayload(
                    user_id=user_id,
                    transaction_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                    amount=credits_to_charge,
                    description=description or self._build_sandbox_operation_description(
                        operation=normalized_operation,
                        credits_charged=credits_to_charge,
                    ),
                    feature_id=f"sandbox.{normalized_operation}",
                    workspace_id=workspace_id,
                    task_id=task_id,
                    metadata=tx_metadata,
                )
            )
        if tx is None:
            raise ValueError("Credit transaction was not recorded")
        recorded_metadata = self._transaction_metadata(tx)
        recorded_charge = self._transaction_charge(tx, credits_to_charge)
        return SandboxOperationCreditConsumption(
            operation=str(recorded_metadata.get("operation") or normalized_operation),
            credits_charged=recorded_charge,
            transaction_id=str(tx.id),
            balance_after=int(tx.balance_after),
            charged=recorded_charge > 0,
        )

    async def refund_failed_task(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
        reason: str = "任务失败退款",
        task_id: str | None = None,
    ) -> Any | None:
        """Refund a failed workflow task consume transaction."""
        return await self.refund_consumption(
            user_id=user_id,
            original_transaction_id=original_transaction_id,
            reason=reason,
            task_id=task_id,
        )

    async def refund_consumption(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
        reason: str = "扣费退款",
        task_id: str | None = None,
    ) -> Any | None:
        """Refund a refundable consume transaction."""
        async with self._client() as client:
            return await client.refund_credit_consumption(
                CreditRefundPayload(
                    user_id=user_id,
                    original_transaction_id=original_transaction_id,
                    reason=reason,
                    task_id=task_id,
                )
            )

    async def admin_grant(
        self,
        *,
        admin_id: str,
        target_user_id: str,
        amount: int,
        description: str = "管理员发放积分",
    ) -> Any:
        """Grant credits to user."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        async with self._client() as client:
            return await client.admin_adjust_credit(
                CreditAdminAdjustPayload(
                    target_user_id=target_user_id,
                    transaction_type=CreditTransactionType.ADMIN_GRANT.value,
                    amount=amount,
                    description=description,
                    admin_id=admin_id,
                )
            )

    async def admin_deduct(
        self,
        *,
        admin_id: str,
        target_user_id: str,
        amount: int,
        description: str = "管理员扣除积分",
    ) -> Any:
        """Deduct credits from user."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        actual_deduction = amount
        async with self._client() as client:
            return await client.admin_adjust_credit(
                CreditAdminAdjustPayload(
                    target_user_id=target_user_id,
                    transaction_type=CreditTransactionType.ADMIN_DEDUCT.value,
                    amount=-actual_deduction,
                    description=description,
                    admin_id=admin_id,
                    metadata={
                        "requested_amount": amount,
                        "actual_deduction": actual_deduction,
                    },
                )
            )

    async def grant_registration_bonus(
        self,
        *,
        user_id: str,
        amount: int = REGISTRATION_BONUS,
    ) -> Any:
        """Grant registration bonus credits."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        async with self._client() as client:
            return await client.admin_adjust_credit(
                CreditAdminAdjustPayload(
                    target_user_id=user_id,
                    transaction_type=CreditTransactionType.REGISTRATION_BONUS.value,
                    amount=amount,
                    description=f"注册奖励 +{amount} 积分",
                    admin_id=None,
                )
            )

    def _parse_transaction_type(
        self,
        transaction_type: str | None,
    ) -> str | None:
        if not transaction_type:
            return None
        try:
            return CreditTransactionType(transaction_type).value
        except ValueError as exc:
            raise ValueError(f"Unsupported transaction type: {transaction_type}") from exc

    def _build_feature_token_description(
        self,
        *,
        feature_id: str,
        total_tokens: int,
        credits_charged: int,
        free_tokens_applied: int,
    ) -> str:
        if credits_charged <= 0:
            if free_tokens_applied > 0:
                return f"{feature_id} 用量记录（免费额度内）"
            return f"{feature_id} 用量记录"
        return f"{feature_id} 扣费 {credits_charged} 积分"

    def _build_thread_description(
        self,
        *,
        total_tokens: int,
        credits_charged: int,
        free_tokens_applied: int,
    ) -> str:
        if credits_charged <= 0:
            if free_tokens_applied > 0:
                return "主线对话用量记录（免费额度内）"
            return "主线对话用量记录"
        return f"主线对话扣费 {credits_charged} 积分"

    def _build_sandbox_operation_description(
        self,
        *,
        operation: str,
        credits_charged: int,
    ) -> str:
        label = "Sandbox Python" if operation == "run_python" else f"Sandbox {operation}"
        return f"{label} 扣费 {credits_charged} 积分"

    @staticmethod
    def _normalize_sandbox_operation(operation: str) -> str:
        normalized = str(operation or "").strip()
        if normalized != "run_python":
            raise ValueError(f"Unsupported sandbox billing operation: {operation}")
        return normalized

    @classmethod
    def _sandbox_operation_credits(
        cls,
        policy: OperationBillingPolicy,
        operation: str,
    ) -> int:
        normalized_operation = cls._normalize_sandbox_operation(operation)
        if normalized_operation == "run_python":
            return max(int(policy.run_python_credits or 0), 0)
        raise ValueError(f"Unsupported sandbox billing operation: {operation}")

    def _to_dict(self, tx: Any) -> dict[str, Any]:
        return {
            "id": str(tx.id),
            "user_id": str(tx.user_id),
            "type": tx.transaction_type.value if hasattr(tx.transaction_type, "value") else tx.transaction_type,
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
            "description": tx.description,
            "feature_id": tx.feature_id,
            "workspace_id": tx.workspace_id,
            "task_id": tx.task_id,
            "admin_id": tx.admin_id,
            "metadata": getattr(tx, "tx_metadata", None) or getattr(tx, "metadata", None) or {},
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }

    def _to_public_dict(self, tx: Any) -> dict[str, Any]:
        item = self._to_dict(tx)
        item["metadata"] = self._public_metadata(item.get("metadata"))
        return item

    @staticmethod
    def _public_metadata(metadata: Any) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        metadata_type = metadata.get("type")
        public: dict[str, Any] = {}
        if isinstance(metadata_type, str):
            public["type"] = metadata_type
        for key in (
            "credits_charged",
            "operation",
            "model_name",
            "source",
            "workspace_type",
            "execution_id",
            "user_message_id",
            "node_id",
        ):
            value = metadata.get(key)
            if value is not None:
                public[key] = value
        return public
