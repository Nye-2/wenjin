"""Credit command/query service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.credit import CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRuleType
from src.dataservice.domains.credit.repository import CreditRepository


class DataServiceCreditService:
    """DataService-owned credit persistence operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = CreditRepository(session)

    async def list_grant_rules(self) -> list[Any]:
        return await self.repository.list_grant_rules()

    async def get_grant_rule(self, rule_id: str) -> Any | None:
        return await self.repository.get_grant_rule(rule_id)

    async def get_balance(self, user_id: str) -> int | None:
        return await self.repository.get_user_credit_balance(user_id)

    async def get_credit_summary(self, user_id: str) -> dict[str, int] | None:
        user = await self.repository.get_user(user_id)
        if user is None:
            return None
        return {
            "credits": int(user.credits),
            "total_earned": int(user.total_credits_earned),
            "total_spent": int(user.total_credits_spent),
        }

    async def get_admin_credit_summary(self) -> dict[str, int]:
        return await self.repository.get_admin_credit_summary()

    async def get_thread_token_usage_summary(self) -> dict[str, int]:
        transactions = await self.repository.list_thread_token_transactions()
        refunded_ids = {
            str(tx.tx_metadata.get("original_transaction_id"))
            for tx in transactions
            if tx.transaction_type == CreditTransactionType.REFUND
            and isinstance(tx.tx_metadata, dict)
            and tx.tx_metadata.get("original_transaction_id")
        }

        total_tokens = 0
        transaction_count = 0
        user_ids: set[str] = set()
        for tx in transactions:
            if tx.transaction_type != CreditTransactionType.THREAD_TOKEN_CONSUME:
                continue
            if str(tx.id) in refunded_ids:
                continue
            metadata = tx.tx_metadata if isinstance(tx.tx_metadata, dict) else {}
            token_usage = metadata.get("token_usage")
            if not isinstance(token_usage, dict):
                continue
            total_tokens += max(int(token_usage.get("total_tokens", 0) or 0), 0)
            transaction_count += 1
            user_ids.add(str(tx.user_id))
        return {
            "total_tokens": total_tokens,
            "transactions": transaction_count,
            "users": len(user_ids),
        }

    async def aggregate_credit_consumption_stats(
        self,
        *,
        since: datetime,
        granularity: str,
    ) -> dict[str, Any]:
        inflow_types = {
            CreditTransactionType.ADMIN_GRANT,
            CreditTransactionType.REGISTRATION_BONUS,
            CreditTransactionType.REFUND,
            CreditTransactionType.REFERRAL_BONUS,
            CreditTransactionType.REDEEM_CODE,
        }
        rows = await self.repository.aggregate_credit_transactions_by_bucket(
            since=since,
            granularity=granularity,
        )
        series_by_bucket: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = row.bucket.isoformat()
            ttype = row.ttype if isinstance(row.ttype, str) else row.ttype.value
            amount = int(row.total)
            series_by_bucket.setdefault(
                bucket,
                {"date": bucket, "inflow": 0, "outflow": 0, "by_type": {}},
            )
            try:
                ttype_enum = CreditTransactionType(ttype)
            except ValueError:
                continue
            if ttype_enum in inflow_types:
                series_by_bucket[bucket]["inflow"] += amount
            else:
                series_by_bucket[bucket]["outflow"] += abs(amount)
            series_by_bucket[bucket]["by_type"][ttype] = amount

        summary = await self.repository.get_admin_credit_summary()
        return {
            "kpis": {
                "total_issued": summary["total_issued"],
                "total_spent": summary["total_spent"],
                "current_pool": summary["in_circulation"],
            },
            "credit_series": [
                series_by_bucket[key] for key in sorted(series_by_bucket)
            ],
        }

    async def get_credit_history(
        self,
        *,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        transaction_type: CreditTransactionType | None = None,
    ) -> tuple[list[Any], int]:
        return await self.repository.list_credit_transactions(
            user_id=user_id,
            transaction_type=transaction_type,
            limit=limit,
            offset=offset,
        )

    async def get_consumed_tokens(
        self,
        *,
        user_id: str,
        consume_type: CreditTransactionType,
        metadata_type: str | None = None,
    ) -> int:
        transactions = await self.repository.list_token_accounting_transactions(
            user_id=user_id,
            consume_type=consume_type,
        )
        refunded_ids = {
            str(tx.tx_metadata.get("original_transaction_id"))
            for tx in transactions
            if tx.transaction_type == CreditTransactionType.REFUND
            and tx.tx_metadata.get("original_transaction_id")
        }

        total = 0
        for tx in transactions:
            if tx.transaction_type != consume_type:
                continue
            if str(tx.id) in refunded_ids:
                continue
            metadata = tx.tx_metadata or {}
            if metadata_type is not None and (
                not isinstance(metadata, dict) or metadata.get("type") != metadata_type
            ):
                continue
            token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else {}
            if isinstance(token_usage, dict):
                total += max(int(token_usage.get("total_tokens", 0) or 0), 0)
        return total

    async def get_user_for_update(self, user_id: str) -> Any | None:
        return await self.repository.get_user_for_update(user_id)

    async def create_grant_rule(
        self,
        *,
        name: str,
        rule_type: CreditGrantRuleType,
        amount: int,
        config: dict[str, Any],
        description: str | None,
        admin_id: str,
    ) -> Any:
        rule = self.repository.create_grant_rule(
            {
                "name": name,
                "rule_type": rule_type,
                "amount": amount,
                "description": description,
                "config": dict(config),
                "enabled": True,
                "created_by_admin_id": admin_id,
            }
        )
        await self._finish(rule)
        return rule

    async def update_grant_rule(
        self,
        *,
        rule_id: str,
        name: str,
        amount: int,
        config: dict[str, Any],
        description: str | None,
    ) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        rule.name = name
        rule.amount = amount
        rule.description = description
        rule.config = dict(config)
        await self._finish(rule)
        return rule

    async def toggle_grant_rule(self, rule_id: str) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        rule.enabled = not bool(rule.enabled)
        await self._finish(rule)
        return rule

    async def delete_grant_rule(self, rule_id: str) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        await self.repository.delete_grant_rule(rule)
        await self._finish()
        return rule

    async def get_active_grant_rule(self, rule_type: CreditGrantRuleType) -> Any | None:
        return await self.repository.get_active_grant_rule(rule_type)

    async def list_enabled_periodic_grant_rules(self) -> list[Any]:
        return await self.repository.list_enabled_grant_rules(
            CreditGrantRuleType.PERIODIC
        )

    async def apply_registration_bonus_from_rule(self, *, user_id: str, rule: Any) -> Any:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("user not found")
        amount = int(rule.amount)
        user.credits = int(user.credits or 0) + amount
        user.total_credits_earned = int(user.total_credits_earned or 0) + amount
        tx = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": CreditTransactionType.REGISTRATION_BONUS,
                "amount": amount,
                "balance_after": user.credits,
                "description": f"注册奖励 (rule {str(rule.id)[:8]}***)",
            }
        )
        await self._finish(tx)
        return tx

    async def apply_periodic_grant_rule(self, *, rule: Any, now: Any) -> int:
        target_filter = rule.config.get("target_filter", {}) if isinstance(rule.config, dict) else {}
        active_since = None
        active_within_days = target_filter.get("active_within_days")
        if active_within_days is not None:
            active_since = now - timedelta(days=int(active_within_days))
        users = await self.repository.list_users_for_periodic_credit_filter(
            active_since=active_since,
            role=target_filter.get("role"),
        )
        amount = int(rule.amount)
        for user in users:
            user.credits = int(user.credits or 0) + amount
            user.total_credits_earned = int(user.total_credits_earned or 0) + amount
            self.repository.create_credit_transaction(
                {
                    "user_id": user.id,
                    "transaction_type": CreditTransactionType.ADMIN_GRANT,
                    "amount": amount,
                    "balance_after": user.credits,
                    "description": f"周期发放（rule {str(rule.id)[:8]}***）",
                }
            )
        rule.last_triggered_at = now
        await self._finish()
        return len(users)

    async def record_consumption(
        self,
        *,
        user_id: str,
        transaction_type: CreditTransactionType,
        amount: int,
        description: str,
        feature_id: str | None = None,
        workspace_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("User not found")
        balance_before = int(user.credits)
        credits_to_charge = max(int(amount), 0)
        if credits_to_charge > 0:
            user.credits -= credits_to_charge
            user.total_credits_spent += credits_to_charge
        tx = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": transaction_type,
                "amount": -credits_to_charge,
                "balance_after": user.credits,
                "description": description,
                "feature_id": feature_id,
                "workspace_id": workspace_id,
                "task_id": task_id,
                "tx_metadata": dict(metadata or {}),
            }
        )
        await self._finish(tx)
        return tx, balance_before

    async def refund_consumption(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
        reason: str,
        task_id: str | None = None,
    ) -> Any | None:
        original_tx = await self.repository.get_credit_transaction(original_transaction_id)
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

        existing_refund = await self.repository.find_refund_for_original(
            user_id=user_id,
            original_transaction_id=original_transaction_id,
        )
        if existing_refund is not None:
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

        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("User not found")
        if refund_amount > 0:
            user.credits += refund_amount
            user.total_credits_spent = max(0, int(user.total_credits_spent) - refund_amount)

        refund_tx = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": CreditTransactionType.REFUND,
                "amount": refund_amount,
                "balance_after": user.credits,
                "description": reason,
                "feature_id": original_tx.feature_id,
                "workspace_id": original_tx.workspace_id,
                "task_id": task_id or original_tx.task_id,
                "tx_metadata": {
                    "original_transaction_id": original_transaction_id,
                    "original_task_id": original_tx.task_id,
                    "original_transaction_type": original_tx.transaction_type.value,
                    "token_usage": original_metadata.get("token_usage"),
                },
            }
        )
        await self._finish(refund_tx)
        return refund_tx

    async def admin_adjust(
        self,
        *,
        admin_id: str | None,
        target_user_id: str,
        amount: int,
        transaction_type: CreditTransactionType,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        user = await self.repository.get_user_for_update(target_user_id)
        if user is None:
            raise ValueError("User not found")
        signed_amount = int(amount)
        if signed_amount > 0:
            user.credits += signed_amount
            user.total_credits_earned += signed_amount
        else:
            user.credits += signed_amount
            user.total_credits_spent = int(user.total_credits_spent) + abs(signed_amount)
        tx = self.repository.create_credit_transaction(
            {
                "user_id": target_user_id,
                "transaction_type": transaction_type,
                "amount": signed_amount,
                "balance_after": user.credits,
                "description": description,
                "admin_id": admin_id,
                "tx_metadata": dict(metadata or {}),
            }
        )
        await self._finish(tx)
        return tx

    async def create_redeem_code(
        self,
        *,
        code: str,
        amount: int,
        max_uses: int,
        per_user_limit: int,
        expires_at: datetime | None,
        description: str | None,
        admin_id: str,
        batch_id: str,
    ) -> Any:
        record = self.repository.create_redeem_code(
            {
                "code": code,
                "amount": amount,
                "max_uses": max_uses,
                "use_count": 0,
                "per_user_limit": per_user_limit,
                "expires_at": expires_at,
                "valid_from": None,
                "enabled": True,
                "batch_id": batch_id,
                "description": description,
                "created_by_admin_id": admin_id,
            }
        )
        await self.session.flush()
        return record

    async def list_redeem_codes(
        self,
        *,
        batch_id: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        return await self.repository.list_redeem_codes(
            batch_id=batch_id,
            enabled=enabled,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    async def disable_redeem_code(self, code_id: str) -> Any | None:
        code = await self.repository.get_redeem_code(code_id)
        if code is None:
            return None
        code.enabled = False
        await self._finish(code)
        return code

    async def redeem_code(self, *, code: str, user_id: str) -> Any:
        async with self.session.begin():
            row = await self.repository.get_redeem_code_for_update(code)
            if row is None:
                raise ValueError("code not found")
            if not row.enabled:
                raise ValueError("code disabled")
            now = datetime.now(UTC)
            if row.expires_at and row.expires_at < now:
                raise ValueError("code expired")
            if row.valid_from and row.valid_from > now:
                raise ValueError("code not yet valid")
            if row.use_count >= row.max_uses:
                raise ValueError("code exhausted")

            user_uses = await self.repository.count_redemptions_for_user(
                code_id=row.id,
                user_id=user_id,
            )
            if user_uses >= row.per_user_limit:
                raise ValueError("per-user limit reached")

            user = await self.repository.get_user_for_update(user_id)
            if user is None:
                raise ValueError("user not found")

            new_balance = int(user.credits or 0) + int(row.amount)
            user.credits = new_balance
            user.total_credits_earned = int(user.total_credits_earned or 0) + int(row.amount)

            txn = self.repository.create_credit_transaction(
                {
                    "user_id": user_id,
                    "transaction_type": CreditTransactionType.REDEEM_CODE,
                    "amount": row.amount,
                    "balance_after": new_balance,
                    "description": f"兑换码 {row.code[:9]}***",
                }
            )
            await self.session.flush()

            self.repository.create_redemption(
                {
                    "code_id": row.id,
                    "user_id": user_id,
                    "transaction_id": txn.id,
                }
            )
            row.use_count += 1
        return txn

    async def record_referral(
        self,
        *,
        referrer_user_id: str,
        referee_user_id: str,
    ) -> Any:
        referral = self.repository.create_referral(
            {
                "referrer_user_id": referrer_user_id,
                "referee_user_id": referee_user_id,
            }
        )
        await self._finish(referral)
        return referral

    async def get_referral_by_referee(self, referee_user_id: str) -> Any | None:
        return await self.repository.get_referral_by_referee(referee_user_id)

    async def apply_referee_signup_bonus(self, *, referee_user_id: str) -> Any | None:
        referral = await self.repository.get_referral_by_referee(referee_user_id)
        if referral is None:
            return None
        rule = await self.repository.get_active_grant_rule(
            CreditGrantRuleType.REFERRAL_REFERRED
        )
        if rule is None:
            return None
        config = rule.config if isinstance(rule.config, dict) else {}
        if config.get("trigger") != "on_signup":
            return None
        return await self._grant_referral_bonus(
            user_id=referee_user_id,
            amount=int(rule.amount),
            description="邀请奖励：作为被邀请者",
            mark_field="referee_credited_at",
            referral=referral,
        )

    async def apply_referrer_first_task_bonus(self, *, referee_user_id: str) -> Any | None:
        referral = await self.repository.get_referral_by_referee(referee_user_id)
        if referral is None:
            return None
        if referral.referee_first_task_at is not None:
            return None
        referral.referee_first_task_at = datetime.now(UTC)
        rule = await self.repository.get_active_grant_rule(
            CreditGrantRuleType.REFERRAL_REFERRER
        )
        if rule is None:
            await self._finish(referral)
            return None
        config = rule.config if isinstance(rule.config, dict) else {}
        if config.get("trigger") != "on_first_task":
            await self._finish(referral)
            return None
        return await self._grant_referral_bonus(
            user_id=referral.referrer_user_id,
            amount=int(rule.amount),
            description=f"邀请奖励：被邀请者 {referee_user_id[:8]}*** 首次完成任务",
            mark_field="referrer_credited_at",
            referral=referral,
        )

    async def _grant_referral_bonus(
        self,
        *,
        user_id: str,
        amount: int,
        description: str,
        mark_field: str,
        referral: Any,
    ) -> Any:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError(f"user {user_id} not found")
        user.credits = int(user.credits or 0) + amount
        user.total_credits_earned = int(user.total_credits_earned or 0) + amount
        txn = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": CreditTransactionType.REFERRAL_BONUS,
                "amount": amount,
                "balance_after": user.credits,
                "description": description,
            }
        )
        setattr(referral, mark_field, datetime.now(UTC))
        await self._finish(txn)
        return txn

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
