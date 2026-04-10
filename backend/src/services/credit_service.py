"""Credit service for balance management and credit ledger operations."""

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.config_loader import get_app_config
from src.database import CreditTransaction, CreditTransactionType, User
from src.services.chat_billing import TokenUsage
from src.services.feature_credit_policy import (
    FEATURE_COSTS as WORKFLOW_CREDIT_COSTS,
)
from src.services.feature_credit_policy import (
    FEATURE_DISPLAY_NAMES,
    THESIS_ACTION_LABELS,
    get_feature_cost,
)

REGISTRATION_BONUS = 100


@dataclass(slots=True)
class ChatBillingPolicy:
    """Configurable chat token billing policy."""

    enabled: bool
    free_tokens: int
    tokens_per_credit: int


@dataclass(slots=True)
class ChatCreditConsumption:
    """Result of settling one chat turn against the credit ledger."""

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
        """Return persisted billing metadata for chat messages."""
        return {
            "type": "chat_token_billing",
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


class InsufficientCreditsError(Exception):
    """Raised when user has insufficient credits for an operation."""

    def __init__(self, current_balance: int, required: int):
        self.current_balance = current_balance
        self.required = required
        super().__init__(f"Insufficient credits: balance={current_balance}, required={required}")


class CreditService:
    """Credit accounting service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_feature_cost(feature_id: str, action: str | None = None) -> int:
        """Resolve credit cost for a feature and optional action."""
        return get_feature_cost(feature_id, action)

    @staticmethod
    def get_chat_billing_policy() -> ChatBillingPolicy:
        """Return the configured chat token billing policy."""
        chat_config = get_app_config().billing.chat
        return ChatBillingPolicy(
            enabled=bool(chat_config.enabled),
            free_tokens=max(int(chat_config.free_tokens), 0),
            tokens_per_credit=max(int(chat_config.tokens_per_credit), 1),
        )

    @classmethod
    def get_workflow_costs(cls) -> dict[str, Any]:
        """Expose workflow and chat billing configuration."""
        policy = cls.get_chat_billing_policy()
        return {
            **WORKFLOW_CREDIT_COSTS,
            "chat_token_billing": {
                "enabled": policy.enabled,
                "free_tokens": policy.free_tokens,
                "tokens_per_credit": policy.tokens_per_credit,
            },
        }

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

    async def consume_for_feature(
        self,
        *,
        user_id: str,
        feature_id: str,
        action: str | None = None,
        workspace_id: str | None = None,
        task_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreditTransaction | None:
        """Consume credits for feature execution."""
        cost = self.get_feature_cost(feature_id, action)
        if cost <= 0:
            return None

        user = await self._get_user_for_update(user_id)
        if user.credits < cost:
            raise InsufficientCreditsError(int(user.credits), cost)

        user.credits -= cost
        user.total_credits_spent += cost

        tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=-cost,
            balance_after=user.credits,
            description=description or self._build_consume_description(feature_id, action),
            feature_id=feature_id,
            workspace_id=workspace_id,
            task_id=task_id,
            tx_metadata=metadata or {},
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def get_consumed_chat_tokens(self, user_id: str) -> int:
        """Return successfully settled historical chat tokens for a user."""
        result = await self.db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type.in_(
                    [
                        CreditTransactionType.CHAT_TOKEN_CONSUME,
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
            if tx.transaction_type != CreditTransactionType.CHAT_TOKEN_CONSUME:
                continue
            if str(tx.id) in refunded_ids:
                continue
            metadata = tx.tx_metadata or {}
            token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else {}
            if isinstance(token_usage, dict):
                total += max(int(token_usage.get("total_tokens", 0) or 0), 0)
        return total

    async def can_start_chat_turn(self, user_id: str) -> bool:
        """Return whether the user can start a billable chat turn.

        Uses ``SELECT ... FOR UPDATE`` on the user row so that concurrent
        requests serialise on the same balance, preventing two callers from
        both passing the check before either deducts credits.
        """
        policy = self.get_chat_billing_policy()
        if not policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_chat_tokens(user_id)
        if consumed_tokens < policy.free_tokens:
            return True

        # Lock the user row to prevent concurrent budget checks from both
        # passing before either has a chance to deduct credits.
        user = await self._get_user_for_update(user_id)
        return int(user.credits) > 0

    async def consume_for_chat_usage(
        self,
        *,
        user_id: str,
        token_usage: TokenUsage | dict[str, int],
        model_name: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatCreditConsumption:
        """Consume credits for a completed chat turn based on token usage."""
        policy = self.get_chat_billing_policy()
        if isinstance(token_usage, TokenUsage):
            normalized_usage = token_usage.as_dict()
        else:
            normalized_usage = {
                "input_tokens": max(int(token_usage.get("input_tokens", 0) or 0), 0),
                "output_tokens": max(int(token_usage.get("output_tokens", 0) or 0), 0),
                "total_tokens": max(int(token_usage.get("total_tokens", 0) or 0), 0),
            }
        if normalized_usage["total_tokens"] <= 0:
            normalized_usage["total_tokens"] = (
                normalized_usage["input_tokens"] + normalized_usage["output_tokens"]
            )

        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_chat_tokens(user_id)
        historical_tokens_after = historical_tokens_before + total_tokens

        if not policy.enabled or total_tokens <= 0:
            return ChatCreditConsumption(
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

        overage_before = max(historical_tokens_before - policy.free_tokens, 0)
        overage_after = max(historical_tokens_after - policy.free_tokens, 0)
        billable_tokens = max(overage_after - overage_before, 0)
        free_tokens_applied = max(total_tokens - billable_tokens, 0)
        credits_to_charge = (
            math.ceil(billable_tokens / policy.tokens_per_credit)
            if billable_tokens > 0
            else 0
        )

        MAX_OVERDRAFT = 100  # safety net: never let balance go below -100
        user = await self._get_user_for_update(user_id)
        balance_before = int(user.credits)
        if credits_to_charge > 0:
            max_charge = balance_before + MAX_OVERDRAFT
            credits_to_charge = min(credits_to_charge, max(0, max_charge))
            user.credits -= credits_to_charge
            user.total_credits_spent += credits_to_charge

        tx_metadata = {
            "token_usage": normalized_usage,
            "thread_id": thread_id,
            "balance_before": balance_before,
            "policy": {
                "free_tokens": policy.free_tokens,
                "tokens_per_credit": policy.tokens_per_credit,
            },
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": free_tokens_applied,
            "billable_tokens": billable_tokens,
            "model_name": model_name,
            "overdraft_credits": max(credits_to_charge - max(balance_before, 0), 0),
        }
        if metadata:
            tx_metadata.update(metadata)

        tx = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.CHAT_TOKEN_CONSUME,
            amount=-credits_to_charge,
            balance_after=user.credits,
            description=description or self._build_chat_description(
                total_tokens=total_tokens,
                credits_charged=credits_to_charge,
                free_tokens_applied=free_tokens_applied,
            ),
            feature_id="chat",
            workspace_id=workspace_id,
            task_id=None,
            tx_metadata=tx_metadata,
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return ChatCreditConsumption(
            token_usage=normalized_usage,
            model_name=model_name,
            free_tokens_applied=free_tokens_applied,
            billable_tokens=billable_tokens,
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
                CreditTransactionType.CHAT_TOKEN_CONSUME,
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

        refund_amount = abs(int(original_tx.amount))
        if refund_amount <= 0 and original_tx.transaction_type != CreditTransactionType.CHAT_TOKEN_CONSUME:
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
                "token_usage": (
                    original_tx.tx_metadata.get("token_usage")
                    if isinstance(original_tx.tx_metadata, dict)
                    else None
                ),
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

    def _build_consume_description(self, feature_id: str, action: str | None) -> str:
        base = FEATURE_DISPLAY_NAMES.get(feature_id, feature_id)
        if feature_id == "thesis_writing" and action:
            action_label = THESIS_ACTION_LABELS.get(action, action)
            return f"{base} - {action_label}"
        return f"{base} 执行消耗"

    def _build_chat_description(
        self,
        *,
        total_tokens: int,
        credits_charged: int,
        free_tokens_applied: int,
    ) -> str:
        if credits_charged <= 0:
            if free_tokens_applied > 0:
                return f"Chat token 用量记录（{total_tokens} tokens，免费额度内）"
            return f"Chat token 用量记录（{total_tokens} tokens）"
        return f"Chat token 扣费（{total_tokens} tokens）"

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
