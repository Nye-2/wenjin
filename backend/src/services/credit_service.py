"""Credit service for balance management and credit ledger operations."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import CreditTransaction, CreditTransactionType, User
from src.services.billing_policy import (
    TokenBillingPolicy,
    calculate_token_billing_charge,
    get_feature_token_billing_policy,
    get_thread_token_billing_policy,
)
from src.services.billing_policy import (
    get_workflow_costs as get_billing_workflow_costs,
)
from src.services.thread_billing import (
    TokenUsage,
    normalize_token_usage,
)

REGISTRATION_BONUS = 100


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


class CreditService:
    """Credit accounting service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_thread_billing_policy() -> TokenBillingPolicy:
        """Return the configured thread token billing policy."""
        return get_thread_token_billing_policy()

    @staticmethod
    def get_feature_billing_policy() -> TokenBillingPolicy:
        """Return the configured workspace feature token billing policy."""
        return get_feature_token_billing_policy()

    @classmethod
    def get_workflow_costs(cls) -> dict[str, Any]:
        """Expose workflow and thread billing configuration."""
        return get_billing_workflow_costs()

    async def get_balance(self, user_id: str) -> int:
        """Get user current credit balance."""
        result = await self.db.execute(select(User.credits).where(User.id == user_id))
        balance = result.scalar_one_or_none()
        if balance is None:
            raise ValueError("User not found")
        return int(balance)

    async def get_credit_summary(self, user_id: str) -> dict[str, int]:
        """Get user credit summary."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        return {
            "credits": int(user.credits),
            "total_earned": int(user.total_credits_earned),
            "total_spent": int(user.total_credits_spent),
        }

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

        base_query = select(CreditTransaction).where(CreditTransaction.user_id == user_id)
        if tx_type:
            base_query = base_query.where(CreditTransaction.transaction_type == tx_type)

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        result = await self.db.execute(
            base_query
            .order_by(desc(CreditTransaction.created_at))
            .offset(offset)
            .limit(limit)
        )
        transactions = result.scalars().all()
        return [self._to_dict(tx) for tx in transactions], int(total)

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

        base_query = select(CreditTransaction)
        if user_id:
            base_query = base_query.where(CreditTransaction.user_id == user_id)
        if tx_type:
            base_query = base_query.where(CreditTransaction.transaction_type == tx_type)

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        result = await self.db.execute(
            base_query
            .order_by(desc(CreditTransaction.created_at))
            .offset(offset)
            .limit(limit)
        )
        transactions = result.scalars().all()
        return [self._to_dict(tx) for tx in transactions], int(total)

    async def get_consumed_thread_tokens(self, user_id: str) -> int:
        """Return successfully settled historical thread tokens for a user."""
        result = await self.db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type.in_(
                    [
                        CreditTransactionType.THREAD_TOKEN_CONSUME,
                        CreditTransactionType.REFUND,
                    ]
                ),
            )
        )
        transactions = list(result.scalars().all())
        refunded_ids = {
            str(tx.tx_metadata.get("original_transaction_id"))
            for tx in transactions
            if tx.transaction_type == CreditTransactionType.REFUND
            and tx.tx_metadata.get("original_transaction_id")
        }

        total = 0
        for tx in transactions:
            if tx.transaction_type != CreditTransactionType.THREAD_TOKEN_CONSUME:
                continue
            if str(tx.id) in refunded_ids:
                continue
            metadata = tx.tx_metadata or {}
            token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else {}
            if isinstance(token_usage, dict):
                total += max(int(token_usage.get("total_tokens", 0) or 0), 0)
        return total

    async def get_consumed_feature_tokens(self, user_id: str) -> int:
        """Return successfully settled historical feature-task tokens for a user."""
        result = await self.db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type.in_(
                    [
                        CreditTransactionType.WORKFLOW_CONSUME,
                        CreditTransactionType.REFUND,
                    ]
                ),
            )
        )
        transactions = list(result.scalars().all())
        refunded_ids = {
            str(tx.tx_metadata.get("original_transaction_id"))
            for tx in transactions
            if tx.transaction_type == CreditTransactionType.REFUND
            and tx.tx_metadata.get("original_transaction_id")
        }

        total = 0
        for tx in transactions:
            if tx.transaction_type != CreditTransactionType.WORKFLOW_CONSUME:
                continue
            if str(tx.id) in refunded_ids:
                continue
            metadata = tx.tx_metadata or {}
            if not isinstance(metadata, dict) or metadata.get("type") != "feature_token_billing":
                continue
            token_usage = metadata.get("token_usage")
            if isinstance(token_usage, dict):
                total += max(int(token_usage.get("total_tokens", 0) or 0), 0)
        return total

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

        # Lock the user row to prevent concurrent budget checks from both
        # passing before either has a chance to deduct credits.
        user = await self._get_user_for_update(user_id)
        return int(user.credits) > 0

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

        user = await self._get_user_for_update(user_id)
        return int(user.credits) > 0

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

        user = await self._get_user_for_update(user_id)
        balance_before = int(user.credits)
        credits_to_charge = charge.credits_to_charge
        if credits_to_charge > 0:
            max_charge = balance_before + policy.max_overdraft_credits
            credits_to_charge = min(credits_to_charge, max(0, max_charge))
            user.credits -= credits_to_charge
            user.total_credits_spent += credits_to_charge

        tx_metadata = {
            "token_usage": normalized_usage,
            "thread_id": thread_id,
            "balance_before": balance_before,
            "policy": policy.as_dict(),
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": charge.free_tokens_applied,
            "billable_tokens": charge.billable_tokens,
            "model_name": model_name,
            "overdraft_credits": max(credits_to_charge - max(balance_before, 0), 0),
        }
        if metadata:
            tx_metadata.update(metadata)

        tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.THREAD_TOKEN_CONSUME,
            amount=-credits_to_charge,
            balance_after=user.credits,
            description=description or self._build_thread_description(
                total_tokens=total_tokens,
                credits_charged=credits_to_charge,
                free_tokens_applied=charge.free_tokens_applied,
            ),
            feature_id="thread",
            workspace_id=workspace_id,
            task_id=None,
            tx_metadata=tx_metadata,
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return ThreadCreditConsumption(
            token_usage=normalized_usage,
            model_name=model_name,
            free_tokens_applied=charge.free_tokens_applied,
            billable_tokens=charge.billable_tokens,
            credits_charged=credits_to_charge,
            historical_tokens_before=historical_tokens_before,
            historical_tokens_after=historical_tokens_after,
            transaction_id=str(tx.id),
            balance_after=int(tx.balance_after),
            charged=credits_to_charge > 0,
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

        user = await self._get_user_for_update(user_id)
        balance_before = int(user.credits)
        credits_to_charge = charge.credits_to_charge
        if credits_to_charge > 0:
            max_charge = balance_before + policy.max_overdraft_credits
            credits_to_charge = min(credits_to_charge, max(0, max_charge))
            user.credits -= credits_to_charge
            user.total_credits_spent += credits_to_charge

        tx_metadata = {
            "type": "feature_token_billing",
            "token_usage": normalized_usage,
            "balance_before": balance_before,
            "policy": policy.as_dict(),
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": charge.free_tokens_applied,
            "billable_tokens": charge.billable_tokens,
            "overdraft_credits": max(credits_to_charge - max(balance_before, 0), 0),
        }
        if metadata:
            tx_metadata.update(metadata)

        tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=-credits_to_charge,
            balance_after=user.credits,
            description=description or self._build_feature_token_description(
                feature_id=feature_id,
                total_tokens=total_tokens,
                credits_charged=credits_to_charge,
                free_tokens_applied=charge.free_tokens_applied,
            ),
            feature_id=feature_id,
            workspace_id=workspace_id,
            task_id=task_id,
            tx_metadata=tx_metadata,
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return FeatureCreditConsumption(
            token_usage=normalized_usage,
            free_tokens_applied=charge.free_tokens_applied,
            billable_tokens=charge.billable_tokens,
            credits_charged=credits_to_charge,
            historical_tokens_before=historical_tokens_before,
            historical_tokens_after=historical_tokens_after,
            transaction_id=str(tx.id),
            balance_after=int(tx.balance_after),
            charged=credits_to_charge > 0,
        )

    async def refund_failed_task(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
        reason: str = "任务失败退款",
        task_id: str | None = None,
    ) -> CreditTransaction | None:
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
    ) -> CreditTransaction | None:
        """Refund a refundable consume transaction."""
        original_tx = await self.db.get(CreditTransaction, original_transaction_id)
        if (
            not original_tx
            or original_tx.user_id != user_id
            or original_tx.transaction_type
            not in {
                CreditTransactionType.WORKFLOW_CONSUME,
                CreditTransactionType.THREAD_TOKEN_CONSUME,
            }
        ):
            return None

        existing_refund = await self.db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == CreditTransactionType.REFUND,
                CreditTransaction.tx_metadata["original_transaction_id"].as_string()
                == original_transaction_id,
            )
        )
        if existing_refund.scalar_one_or_none() is not None:
            return None

        original_metadata = (
            original_tx.tx_metadata
            if isinstance(original_tx.tx_metadata, dict)
            else {}
        )
        is_token_usage_transaction = (
            original_tx.transaction_type == CreditTransactionType.THREAD_TOKEN_CONSUME
            or original_metadata.get("type") == "feature_token_billing"
        )
        refund_amount = abs(int(original_tx.amount))
        if refund_amount <= 0 and not is_token_usage_transaction:
            return None

        user = await self._get_user_for_update(user_id)
        if refund_amount > 0:
            user.credits += refund_amount
            user.total_credits_spent = max(0, int(user.total_credits_spent) - refund_amount)

        refund_tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.REFUND,
            amount=refund_amount,
            balance_after=user.credits,
            description=reason,
            feature_id=original_tx.feature_id,
            workspace_id=original_tx.workspace_id,
            task_id=task_id or original_tx.task_id,
            tx_metadata={
                "original_transaction_id": original_transaction_id,
                "original_task_id": original_tx.task_id,
                "original_transaction_type": original_tx.transaction_type.value,
                "token_usage": original_metadata.get("token_usage"),
            },
        )
        self.db.add(refund_tx)
        await self.db.commit()
        await self.db.refresh(refund_tx)
        return refund_tx

    async def admin_grant(
        self,
        *,
        admin_id: str,
        target_user_id: str,
        amount: int,
        description: str = "管理员发放积分",
    ) -> CreditTransaction:
        """Grant credits to user."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        user = await self._get_user_for_update(target_user_id)
        user.credits += amount
        user.total_credits_earned += amount

        tx = CreditTransaction(
            user_id=target_user_id,
            transaction_type=CreditTransactionType.ADMIN_GRANT,
            amount=amount,
            balance_after=user.credits,
            description=description,
            admin_id=admin_id,
            tx_metadata={},
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def admin_deduct(
        self,
        *,
        admin_id: str,
        target_user_id: str,
        amount: int,
        description: str = "管理员扣除积分",
    ) -> CreditTransaction:
        """Deduct credits from user."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        user = await self._get_user_for_update(target_user_id)
        balance_before = int(user.credits)
        actual_deduction = amount
        user.credits = balance_before - actual_deduction
        user.total_credits_spent = int(user.total_credits_spent) + actual_deduction

        tx = CreditTransaction(
            user_id=target_user_id,
            transaction_type=CreditTransactionType.ADMIN_DEDUCT,
            amount=-actual_deduction,
            balance_after=user.credits,
            description=description,
            admin_id=admin_id,
            tx_metadata={
                "requested_amount": amount,
                "actual_deduction": actual_deduction,
                "balance_before": balance_before,
            },
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def grant_registration_bonus(
        self,
        *,
        user_id: str,
        amount: int = REGISTRATION_BONUS,
    ) -> CreditTransaction:
        """Grant registration bonus credits."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        user = await self._get_user_for_update(user_id)
        user.credits += amount
        user.total_credits_earned += amount

        tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.REGISTRATION_BONUS,
            amount=amount,
            balance_after=user.credits,
            description=f"注册奖励 +{amount} 积分",
            tx_metadata={},
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def _get_user_for_update(self, user_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("User not found")
        return user

    def _parse_transaction_type(
        self,
        transaction_type: str | None,
    ) -> CreditTransactionType | None:
        if not transaction_type:
            return None
        try:
            return CreditTransactionType(transaction_type)
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
                return f"{feature_id} token 用量记录（{total_tokens} tokens，免费额度内）"
            return f"{feature_id} token 用量记录（{total_tokens} tokens）"
        return f"{feature_id} token 扣费（{total_tokens} tokens）"

    def _build_thread_description(
        self,
        *,
        total_tokens: int,
        credits_charged: int,
        free_tokens_applied: int,
    ) -> str:
        if credits_charged <= 0:
            if free_tokens_applied > 0:
                return f"Thread token 用量记录（{total_tokens} tokens，免费额度内）"
            return f"Thread token 用量记录（{total_tokens} tokens）"
        return f"Thread token 扣费（{total_tokens} tokens）"

    def _to_dict(self, tx: CreditTransaction) -> dict[str, Any]:
        return {
            "id": str(tx.id),
            "user_id": str(tx.user_id),
            "type": tx.transaction_type.value,
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
            "description": tx.description,
            "feature_id": tx.feature_id,
            "workspace_id": tx.workspace_id,
            "task_id": tx.task_id,
            "admin_id": tx.admin_id,
            "metadata": tx.tx_metadata or {},
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
