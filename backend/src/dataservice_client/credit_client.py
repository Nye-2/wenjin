"""Credit DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditAdminSummaryPayload,
    CreditConsumptionStatsPayload,
    CreditGrantRuleCreatePayload,
    CreditGrantRulePayload,
    CreditGrantRuleUpdatePayload,
    CreditHistoryPayload,
    CreditPeriodicGrantPagePayload,
    CreditPeriodicGrantPageRequest,
    CreditRedeemCodeCreatePayload,
    CreditRedeemCodePayload,
    CreditRedeemPayload,
    CreditReferralCreatePayload,
    CreditReferralPayload,
    CreditSummaryPayload,
    CreditTokenUsagePayload,
    CreditTransactionPayload,
)


class CreditDataServiceClientMixin:
    """Typed DataService methods for this domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def list_credit_grant_rules(self) -> list[CreditGrantRulePayload]:
        payload = await self._request("GET", "/internal/v1/credit/grant-rules")
        return [CreditGrantRulePayload.model_validate(item) for item in payload["data"]]

    async def get_credit_grant_rule(self, rule_id: str) -> CreditGrantRulePayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/grant-rules/{rule_id}")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def get_active_credit_grant_rule(
        self,
        rule_type: str,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/active-grant-rules/{rule_type}")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def create_credit_grant_rule(
        self,
        command: CreditGrantRuleCreatePayload,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/grant-rules",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def update_credit_grant_rule(
        self,
        rule_id: str,
        command: CreditGrantRuleUpdatePayload,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/credit/grant-rules/{rule_id}",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def toggle_credit_grant_rule(self, rule_id: str) -> CreditGrantRulePayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/grant-rules/{rule_id}/toggle")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def delete_credit_grant_rule(self, rule_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/credit/grant-rules/{rule_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def apply_credit_registration_bonus(
        self,
        user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/users/{user_id}/registration-bonus")
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def get_credit_balance(self, user_id: str) -> int | None:
        payload = await self._request("GET", f"/internal/v1/credit/users/{user_id}/balance")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("balance") is None:
            return None
        return int(data["balance"])

    async def get_credit_summary(self, user_id: str) -> CreditSummaryPayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/users/{user_id}/summary")
        data = payload.get("data")
        return CreditSummaryPayload.model_validate(data) if data is not None else None

    async def process_credit_periodic_grant_page(
        self,
        command: CreditPeriodicGrantPageRequest | None = None,
    ) -> CreditPeriodicGrantPagePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/periodic-grants/process-page",
            json=(command or CreditPeriodicGrantPageRequest()).model_dump(mode="json"),
        )
        return CreditPeriodicGrantPagePayload.model_validate(payload["data"])

    async def get_credit_history(
        self,
        *,
        user_id: str | None = None,
        transaction_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CreditHistoryPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/history",
            params={
                "user_id": user_id,
                "transaction_type": transaction_type,
                "limit": limit,
                "offset": offset,
            },
        )
        return CreditHistoryPayload.model_validate(payload["data"])

    async def get_credit_admin_summary(self) -> CreditAdminSummaryPayload:
        payload = await self._request("GET", "/internal/v1/credit/admin-summary")
        return CreditAdminSummaryPayload.model_validate(payload["data"])

    async def get_credit_thread_token_usage(self) -> CreditTokenUsagePayload:
        payload = await self._request("GET", "/internal/v1/credit/thread-token-usage")
        return CreditTokenUsagePayload.model_validate(payload["data"])

    async def aggregate_credit_consumption_stats(
        self,
        *,
        since: datetime,
        granularity: str = "day",
    ) -> CreditConsumptionStatsPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/consumption-stats",
            params={"since": since.isoformat(), "granularity": granularity},
        )
        return CreditConsumptionStatsPayload.model_validate(payload["data"])

    async def admin_adjust_credit(
        self,
        command: CreditAdminAdjustPayload,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/admin-adjust",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def create_credit_redeem_code(
        self,
        command: CreditRedeemCodeCreatePayload,
    ) -> CreditRedeemCodePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/redeem-codes",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditRedeemCodePayload.model_validate(data) if data is not None else None

    async def list_credit_redeem_codes(
        self,
        *,
        batch_id: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CreditRedeemCodePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/redeem-codes",
            params={
                "batch_id": batch_id,
                "enabled": enabled,
                "keyword": keyword,
                "limit": limit,
                "offset": offset,
            },
        )
        return [CreditRedeemCodePayload.model_validate(item) for item in payload["data"]]

    async def disable_credit_redeem_code(
        self,
        code_id: str,
    ) -> CreditRedeemCodePayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/redeem-codes/{code_id}/disable")
        data = payload.get("data")
        return CreditRedeemCodePayload.model_validate(data) if data is not None else None

    async def redeem_credit_code(
        self,
        command: CreditRedeemPayload,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/redeem",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def record_credit_referral(
        self,
        command: CreditReferralCreatePayload,
    ) -> CreditReferralPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/referrals",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditReferralPayload.model_validate(data) if data is not None else None

    async def get_credit_referral_by_referee(
        self,
        referee_user_id: str,
    ) -> CreditReferralPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/credit/referrals/by-referee/{referee_user_id}",
        )
        data = payload.get("data")
        return CreditReferralPayload.model_validate(data) if data is not None else None

    async def apply_credit_referee_signup_bonus(
        self,
        referee_user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/credit/referrals/{referee_user_id}/apply-referee-signup",
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def apply_credit_referrer_first_task_bonus(
        self,
        referee_user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/credit/referrals/{referee_user_id}/apply-referrer-first-task",
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None
