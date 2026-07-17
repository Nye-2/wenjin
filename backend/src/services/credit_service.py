"""Credit service for balance management and credit ledger operations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.billing.policies import (
    FreeTokenAllowance,
    calculate_free_token_usage,
    calculate_model_usage_credits,
)
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.thread_billing import (
    TokenUsage,
    normalize_token_usage,
)

REGISTRATION_BONUS = 100


@dataclass(slots=True)
class _ResolvedModelBillingPolicy:
    """Resolved pricing state for one model-billed surface."""

    enabled: bool
    free_tokens: int
    global_policy: Any | None
    model_policy: Any | None
    model_policy_config: dict[str, Any]
    policy_metadata: dict[str, Any]


class CreditTransactionType(StrEnum):
    ADMIN_GRANT = "admin_grant"
    ADMIN_DEDUCT = "admin_deduct"
    WORKFLOW_CONSUME = "workflow_consume"
    THREAD_TOKEN_CONSUME = "thread_token_consume"
    REGISTRATION_BONUS = "registration_bonus"
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


class CreditService:
    """Credit accounting service."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

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

    async def get_spendable_balance(self, user_id: str) -> int:
        """Get credits not currently held by active reservations."""
        summary = await self.get_credit_summary(user_id)
        if "spendable_credits" in summary:
            return int(summary["spendable_credits"])
        return int(summary.get("credits", 0)) - int(summary.get("reserved_credits", 0))

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

    async def can_start_thread_turn(self, user_id: str, *, model_name: str) -> bool:
        """Return whether the user can start a billable thread turn.

        Uses ``SELECT ... FOR UPDATE`` on the user row so that concurrent
        requests serialise on the same balance, preventing two callers from
        both passing the check before either deducts credits.
        """
        billing_policy = await self._resolve_model_billing_policy(
            model_name=model_name,
        )
        if not billing_policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_thread_tokens(user_id)
        if consumed_tokens < billing_policy.free_tokens:
            return True

        return await self.get_spendable_balance(user_id) > 0

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

    @staticmethod
    def _policy_int(config: dict[str, Any], key: str, default: int) -> int:
        try:
            return max(int(config.get(key, default) or 0), 0)
        except (TypeError, ValueError):
            return default

    async def _resolve_model_billing_policy(
        self,
        *,
        model_name: str,
    ) -> _ResolvedModelBillingPolicy:
        async with self._client() as client:
            resolved = await client.resolve_model_usage_pricing(model_name)
        model_policy = resolved.model_policy

        config = self._pricing_policy_config(model_policy)
        metadata = self._pricing_policy_metadata(model_policy, config)
        return _ResolvedModelBillingPolicy(
            enabled=True,
            free_tokens=self._policy_int(config, "free_tokens", 0),
            global_policy=resolved.global_policy,
            model_policy=model_policy,
            model_policy_config=config,
            policy_metadata=metadata,
        )

    @staticmethod
    def _pricing_policy_config(policy: Any) -> dict[str, Any]:
        config = getattr(policy, "config", None)
        if isinstance(config, dict):
            return dict(config)
        config_json = getattr(policy, "config_json", None)
        if isinstance(config_json, dict):
            return dict(config_json)
        if isinstance(policy, dict):
            nested = policy.get("config")
            return dict(nested) if isinstance(nested, dict) else dict(policy)
        return {}

    @staticmethod
    def _pricing_policy_metadata(policy: Any, config: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(config)
        for attr in ("id", "policy_key", "policy_kind", "version"):
            value = getattr(policy, attr, None)
            if value is not None:
                metadata[attr] = value.value if hasattr(value, "value") else value
        enabled = getattr(policy, "enabled", None)
        if enabled is not None:
            metadata["enabled"] = bool(enabled)
        return metadata

    async def consume_for_thread_usage(
        self,
        *,
        user_id: str,
        token_usage: TokenUsage | dict[str, int],
        model_name: str,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ThreadCreditConsumption:
        """Consume credits for a completed thread turn based on token usage."""
        billing_policy = await self._resolve_model_billing_policy(
            model_name=str(model_name or "").strip(),
        )
        normalized_usage = self._normalize_usage_dict(token_usage)
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_thread_tokens(user_id)
        free_token_usage = calculate_free_token_usage(
            allowance=FreeTokenAllowance(
                enabled=billing_policy.enabled,
                free_tokens=billing_policy.free_tokens,
            ),
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        model_charge = calculate_model_usage_credits(
            model_policy=billing_policy.model_policy,
            global_policy=billing_policy.global_policy,
            token_usage=normalized_usage,
            surface="chat",
            billable_tokens=free_token_usage.billable_tokens,
        )
        credits_to_charge = model_charge.credits_to_charge
        billable_tokens = model_charge.billable_tokens
        pricing_breakdown = model_charge.breakdown()
        historical_tokens_after = free_token_usage.historical_tokens_after

        if not billing_policy.enabled or total_tokens <= 0:
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

        tx_metadata = {
            "type": "thread_token_billing",
            "token_usage": normalized_usage,
            "thread_id": thread_id,
            "policy": billing_policy.policy_metadata,
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": free_token_usage.free_tokens_applied,
            "billable_tokens": billable_tokens,
            "credits_charged": credits_to_charge,
            "model_name": model_name,
        }
        tx_metadata["pricing_breakdown"] = pricing_breakdown
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
                        free_tokens_applied=free_token_usage.free_tokens_applied,
                    ),
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
                free_token_usage.free_tokens_applied,
            ),
            billable_tokens=self._metadata_int(
                recorded_metadata,
                "billable_tokens",
                billable_tokens,
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

    def _to_dict(self, tx: Any) -> dict[str, Any]:
        return {
            "id": str(tx.id),
            "user_id": str(tx.user_id),
            "type": tx.transaction_type.value if hasattr(tx.transaction_type, "value") else tx.transaction_type,
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
            "description": tx.description,
            "mission_policy_id": tx.mission_policy_id,
            "mission_id": tx.mission_id,
            "operation_key": tx.operation_key,
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
            "mission_id",
            "user_message_id",
            "mission_item_seq",
        ):
            value = metadata.get(key)
            if value is not None:
                public[key] = value
        return public
