"""Credit service for balance management and credit ledger operations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from src.billing.policies import calculate_chat_turn_authorization
from src.contracts.billing import CreditTransactionType
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import CreditAdminAdjustPayload
from src.dataservice_client.provider import dataservice_client


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
        return int(summary["spendable_credits"])

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

    async def preview_thread_turn_capacity(
        self,
        user_id: str,
        *,
        model_name: str,
    ) -> bool:
        """Preview admission; the atomic DataService authorization remains authoritative."""
        summary = await self.get_credit_summary(user_id)
        async with self._client() as client:
            resolved = await client.resolve_model_usage_pricing(model_name)
        model_config = self._pricing_policy_config(resolved.model_policy)
        quote = calculate_chat_turn_authorization(
            model_policy=model_config,
            global_policy=(
                self._pricing_policy_config(resolved.global_policy)
                if resolved.global_policy is not None
                else None
            ),
            historical_tokens=int(summary["thread_consumed_tokens"]),
            reserved_free_tokens=int(summary["reserved_thread_free_tokens"]),
        )
        available_credits = int(summary["spendable_credits"]) + self._policy_int(
            model_config,
            "max_overdraft_credits",
            0,
        )
        return quote.credit_hold <= available_credits

    @staticmethod
    def _policy_int(config: dict[str, Any], key: str, default: int) -> int:
        try:
            return max(int(config.get(key, default) or 0), 0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _pricing_policy_config(policy: Any) -> dict[str, Any]:
        config = policy.config
        if not isinstance(config, dict):
            raise TypeError("Pricing policy config must be an object")
        return dict(config)

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

    def _to_dict(self, tx: Any) -> dict[str, Any]:
        return {
            "id": str(tx.id),
            "user_id": str(tx.user_id),
            "type": tx.transaction_type,
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
            "description": tx.description,
            "mission_policy_id": tx.mission_policy_id,
            "mission_id": tx.mission_id,
            "operation_key": tx.operation_key,
            "workspace_id": tx.workspace_id,
            "task_id": tx.task_id,
            "admin_id": tx.admin_id,
            "idempotency_key": tx.idempotency_key,
            "metadata": dict(tx.metadata),
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
