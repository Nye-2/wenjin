"""Credit service for balance management and credit ledger operations."""

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import CreditTransaction, CreditTransactionType, User
from src.services.feature_credit_policy import (
    FEATURE_COSTS as WORKFLOW_CREDIT_COSTS,
)
from src.services.feature_credit_policy import (
    FEATURE_DISPLAY_NAMES,
    THESIS_ACTION_LABELS,
    get_feature_cost,
)

REGISTRATION_BONUS = 100


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
    def get_workflow_costs() -> dict[str, int | dict[str, int]]:
        """Expose workflow credit cost definitions."""
        return WORKFLOW_CREDIT_COSTS

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

    async def refund_failed_task(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
        reason: str = "任务失败退款",
        task_id: str | None = None,
    ) -> CreditTransaction | None:
        """Refund consumed credits by original consume transaction id."""
        original_tx = await self.db.get(CreditTransaction, original_transaction_id)
        if (
            not original_tx
            or original_tx.user_id != user_id
            or original_tx.transaction_type != CreditTransactionType.WORKFLOW_CONSUME
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
        if refund_amount <= 0:
            return None

        user = await self._get_user_for_update(user_id)
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
        deducted = min(amount, int(user.credits))
        user.credits = max(0, int(user.credits) - amount)

        tx = CreditTransaction(
            user_id=target_user_id,
            transaction_type=CreditTransactionType.ADMIN_DEDUCT,
            amount=-deducted,
            balance_after=user.credits,
            description=description,
            admin_id=admin_id,
            tx_metadata={"requested_amount": amount},
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
