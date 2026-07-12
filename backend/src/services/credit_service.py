"""Credit service for balance management and credit ledger operations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditRefundPayload,
    CreditReservationCreatePayload,
    CreditReservationSettlePayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.billing_policy import (
    OperationBillingPolicy,
    TokenBillingPolicy,
    calculate_mission_estimate,
    calculate_model_usage_credits,
    calculate_sandbox_estimate,
    calculate_token_billing_charge,
    get_mission_token_billing_policy,
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


@dataclass(slots=True)
class _ResolvedModelBillingPolicy:
    """Resolved pricing state for one model-billed surface."""

    enabled: bool
    free_tokens: int
    max_overdraft_credits: int
    global_policy: Any | None
    model_policy: Any | None
    model_policy_config: dict[str, Any]
    policy_metadata: dict[str, Any]
    uses_pricing_policy: bool


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
class MissionCreditConsumption:
    """Result of settling completed Mission work against token usage."""

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
            "type": "mission_token_billing",
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

    @staticmethod
    def get_thread_billing_policy() -> TokenBillingPolicy:
        """Return the configured thread token billing policy."""
        return get_thread_token_billing_policy()

    @staticmethod
    def get_mission_billing_policy() -> TokenBillingPolicy:
        """Return the configured Mission token billing policy."""
        return get_mission_token_billing_policy()

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

    async def get_consumed_mission_tokens(self, user_id: str) -> int:
        """Return successfully settled historical Mission tokens for a user."""
        async with self._client() as client:
            return await client.get_credit_consumed_tokens(
                user_id=user_id,
                consume_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                metadata_type="mission_token_billing",
            )

    async def can_start_thread_turn(self, user_id: str) -> bool:
        """Return whether the user can start a billable thread turn.

        Uses ``SELECT ... FOR UPDATE`` on the user row so that concurrent
        requests serialise on the same balance, preventing two callers from
        both passing the check before either deducts credits.
        """
        policy = self.get_thread_billing_policy()
        billing_policy = await self._resolve_model_billing_policy(
            surface="chat",
            model_name=None,
            base_token_policy=policy,
        )
        if not billing_policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_thread_tokens(user_id)
        if consumed_tokens < billing_policy.free_tokens:
            return True

        return await self.get_spendable_balance(user_id) > 0

    async def can_start_mission(self, user_id: str) -> bool:
        """Return whether the user can start a billable Mission.

        Missions are settled from measured token usage after successful
        execution, so this is an admission-control gate rather than a
        reservation. It prevents zero/negative-balance users from starting new
        work once the configured Mission free-token quota is exhausted.
        """
        policy = self.get_mission_billing_policy()
        billing_policy = await self._resolve_model_billing_policy(
            surface="mission",
            model_name=None,
            base_token_policy=policy,
        )
        if not billing_policy.enabled:
            return True

        consumed_tokens = await self.get_consumed_mission_tokens(user_id)
        if consumed_tokens < billing_policy.free_tokens:
            return True

        return await self.get_spendable_balance(user_id) > 0

    async def can_start_sandbox_operation(self, user_id: str, operation: str) -> bool:
        """Return whether the user can start a fixed-credit sandbox operation."""
        policy = self.get_sandbox_billing_policy()
        credits_to_charge = self._sandbox_operation_credits(policy, operation)
        if not policy.enabled or credits_to_charge <= 0:
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
        surface: str,
        model_name: str | None,
        base_token_policy: TokenBillingPolicy,
    ) -> _ResolvedModelBillingPolicy:
        async with self._client() as client:
            global_policy = await self._first_enabled_pricing_policy(
                client,
                policy_kind="global_credit",
            )
            model_policy = await self._resolve_model_usage_policy(client, model_name=model_name)

        if model_policy is None:
            return _ResolvedModelBillingPolicy(
                enabled=base_token_policy.enabled,
                free_tokens=base_token_policy.free_tokens,
                max_overdraft_credits=base_token_policy.max_overdraft_credits,
                global_policy=global_policy,
                model_policy=None,
                model_policy_config={},
                policy_metadata=base_token_policy.as_dict(),
                uses_pricing_policy=False,
            )

        config = self._pricing_policy_config(model_policy)
        metadata = self._pricing_policy_metadata(model_policy, config)
        return _ResolvedModelBillingPolicy(
            enabled=bool(getattr(model_policy, "enabled", config.get("enabled", True))),
            free_tokens=self._policy_int(config, "free_tokens", 0),
            max_overdraft_credits=self._policy_int(
                config,
                "max_overdraft_credits",
                base_token_policy.max_overdraft_credits,
            ),
            global_policy=global_policy,
            model_policy=model_policy,
            model_policy_config=config,
            policy_metadata=metadata,
            uses_pricing_policy=True,
        )

    async def _first_enabled_pricing_policy(
        self,
        client: Any,
        *,
        policy_kind: str,
    ) -> Any | None:
        if not hasattr(client, "list_pricing_policies"):
            return None
        try:
            policies = await client.list_pricing_policies(
                policy_kind=policy_kind,
                enabled_only=True,
            )
        except Exception:
            return None
        return policies[0] if policies else None

    async def _resolve_model_usage_policy(self, client: Any, *, model_name: str | None) -> Any | None:
        if not hasattr(client, "list_pricing_policies"):
            return None

        pricing_policy_id = self._model_pricing_policy_id(model_name)
        for key in (pricing_policy_id, model_name):
            if not key or not hasattr(client, "get_pricing_policy"):
                continue
            try:
                policy = await client.get_pricing_policy(str(key))
            except Exception:
                policy = None
            if policy is not None and self._is_enabled_model_usage_policy(policy):
                return policy

        return None

    @staticmethod
    def _model_pricing_policy_id(model_name: str | None) -> str | None:
        if not model_name:
            return None
        try:
            from src.services.model_catalog_cache import get_runtime_model_config

            config = get_runtime_model_config(str(model_name))
        except Exception:
            return None
        value = getattr(config, "pricing_policy_id", None) if config is not None else None
        return str(value).strip() if value else None

    @classmethod
    def _is_enabled_model_usage_policy(cls, policy: Any) -> bool:
        policy_kind = getattr(policy, "policy_kind", None)
        kind_value = policy_kind.value if hasattr(policy_kind, "value") else policy_kind
        if kind_value != "model_usage":
            return False
        return bool(getattr(policy, "enabled", True))

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
        model_name: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ThreadCreditConsumption:
        """Consume credits for a completed thread turn based on token usage."""
        policy = self.get_thread_billing_policy()
        billing_policy = await self._resolve_model_billing_policy(
            surface="chat",
            model_name=model_name,
            base_token_policy=policy,
        )
        normalized_usage = self._normalize_usage_dict(token_usage)
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_thread_tokens(user_id)
        free_token_charge = calculate_token_billing_charge(
            policy=TokenBillingPolicy(
                enabled=billing_policy.enabled,
                free_tokens=billing_policy.free_tokens,
                tokens_per_credit=policy.tokens_per_credit,
                max_overdraft_credits=billing_policy.max_overdraft_credits,
            ),
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        if billing_policy.uses_pricing_policy:
            model_charge = calculate_model_usage_credits(
                model_policy=billing_policy.model_policy,
                global_policy=billing_policy.global_policy,
                token_usage=normalized_usage,
                surface="chat",
                billable_tokens=free_token_charge.billable_tokens,
            )
            credits_to_charge = model_charge.credits_to_charge
            billable_tokens = model_charge.billable_tokens
            pricing_breakdown = model_charge.breakdown()
        else:
            credits_to_charge = free_token_charge.credits_to_charge
            billable_tokens = free_token_charge.billable_tokens
            pricing_breakdown = None
        historical_tokens_after = free_token_charge.historical_tokens_after

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
            "free_tokens_applied": free_token_charge.free_tokens_applied,
            "billable_tokens": billable_tokens,
            "credits_charged": credits_to_charge,
            "model_name": model_name,
        }
        if pricing_breakdown is not None:
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
                        free_tokens_applied=free_token_charge.free_tokens_applied,
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
                free_token_charge.free_tokens_applied,
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

    async def consume_for_mission_usage(
        self,
        *,
        user_id: str,
        mission_policy_id: str,
        mission_id: str,
        token_usage: TokenUsage | dict[str, int],
        workspace_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MissionCreditConsumption:
        """Consume credits for completed Mission work based on token usage."""
        policy = self.get_mission_billing_policy()
        model_name = None
        if metadata and metadata.get("model_name"):
            model_name = str(metadata["model_name"])
        billing_policy = await self._resolve_model_billing_policy(
            surface="mission",
            model_name=model_name,
            base_token_policy=policy,
        )
        normalized_usage = self._normalize_usage_dict(token_usage)
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_mission_tokens(user_id)
        free_token_charge = calculate_token_billing_charge(
            policy=TokenBillingPolicy(
                enabled=billing_policy.enabled,
                free_tokens=billing_policy.free_tokens,
                tokens_per_credit=policy.tokens_per_credit,
                max_overdraft_credits=billing_policy.max_overdraft_credits,
            ),
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        if billing_policy.uses_pricing_policy:
            model_charge = calculate_model_usage_credits(
                model_policy=billing_policy.model_policy,
                global_policy=billing_policy.global_policy,
                token_usage=normalized_usage,
                surface="mission",
                billable_tokens=free_token_charge.billable_tokens,
            )
            credits_to_charge = model_charge.credits_to_charge
            billable_tokens = model_charge.billable_tokens
            pricing_breakdown = model_charge.breakdown()
        else:
            credits_to_charge = free_token_charge.credits_to_charge
            billable_tokens = free_token_charge.billable_tokens
            pricing_breakdown = None
        historical_tokens_after = free_token_charge.historical_tokens_after

        if not billing_policy.enabled or total_tokens <= 0:
            return MissionCreditConsumption(
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

        tx_metadata = {
            "type": "mission_token_billing",
            "token_usage": normalized_usage,
            "policy": billing_policy.policy_metadata,
            "historical_tokens_before": historical_tokens_before,
            "historical_tokens_after": historical_tokens_after,
            "free_tokens_applied": free_token_charge.free_tokens_applied,
            "billable_tokens": billable_tokens,
            "credits_charged": credits_to_charge,
        }
        if pricing_breakdown is not None:
            tx_metadata["pricing_breakdown"] = pricing_breakdown
        if metadata:
            tx_metadata.update(metadata)
        tx_metadata["idempotency_key"] = f"mission_token_billing:{mission_id}"

        async with self._client() as client:
            tx, balance_before = await client.record_credit_consumption(
                CreditConsumptionCreatePayload(
                    user_id=user_id,
                    transaction_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                    amount=credits_to_charge,
                    description=description or self._build_mission_token_description(
                        mission_policy_id=mission_policy_id,
                        total_tokens=total_tokens,
                        credits_charged=credits_to_charge,
                        free_tokens_applied=free_token_charge.free_tokens_applied,
                    ),
                    mission_policy_id=mission_policy_id,
                    mission_id=mission_id,
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
        return MissionCreditConsumption(
            token_usage=recorded_usage,
            free_tokens_applied=self._metadata_int(
                recorded_metadata,
                "free_tokens_applied",
                free_token_charge.free_tokens_applied,
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

    async def preview_mission_usage_charge(
        self,
        *,
        user_id: str,
        mission_policy_id: str,
        token_usage: TokenUsage | dict[str, int] | None,
        metadata: dict[str, Any] | None = None,
    ) -> MissionCreditConsumption:
        """Calculate Mission usage credits without writing a ledger transaction."""
        policy = self.get_mission_billing_policy()
        model_name = None
        if metadata and metadata.get("model_name"):
            model_name = str(metadata["model_name"])
        billing_policy = await self._resolve_model_billing_policy(
            surface="mission",
            model_name=model_name,
            base_token_policy=policy,
        )
        normalized_usage = self._normalize_usage_dict(token_usage or {})
        total_tokens = normalized_usage["total_tokens"]
        historical_tokens_before = await self.get_consumed_mission_tokens(user_id)
        free_token_charge = calculate_token_billing_charge(
            policy=TokenBillingPolicy(
                enabled=billing_policy.enabled,
                free_tokens=billing_policy.free_tokens,
                tokens_per_credit=policy.tokens_per_credit,
                max_overdraft_credits=billing_policy.max_overdraft_credits,
            ),
            total_tokens=total_tokens,
            historical_tokens_before=historical_tokens_before,
        )
        if billing_policy.uses_pricing_policy:
            model_charge = calculate_model_usage_credits(
                model_policy=billing_policy.model_policy,
                global_policy=billing_policy.global_policy,
                token_usage=normalized_usage,
                surface="mission",
                billable_tokens=free_token_charge.billable_tokens,
            )
            credits_to_charge = model_charge.credits_to_charge
            billable_tokens = model_charge.billable_tokens
        else:
            credits_to_charge = free_token_charge.credits_to_charge
            billable_tokens = free_token_charge.billable_tokens
        return MissionCreditConsumption(
            token_usage=normalized_usage,
            free_tokens_applied=free_token_charge.free_tokens_applied,
            billable_tokens=billable_tokens,
            credits_charged=credits_to_charge,
            historical_tokens_before=historical_tokens_before,
            historical_tokens_after=free_token_charge.historical_tokens_after,
            transaction_id=None,
            balance_after=None,
            charged=credits_to_charge > 0,
        )

    async def estimate_mission_reservation_credits(
        self,
        *,
        mission_policy_id: str,
        workspace_type: str | None = None,
    ) -> int:
        """Return max reservation credits for a Mission pricing policy."""
        policy = await self._resolve_mission_pricing_policy(
            mission_policy_id=mission_policy_id,
            workspace_type=workspace_type,
        )
        if policy is not None:
            return calculate_mission_estimate(policy).max_charge_credits
        return calculate_mission_estimate(
            {
                "base_fee_credits": 0,
                "estimate_min_credits": 10,
                "estimate_max_credits": 100,
                "max_charge_credits": 100,
            }
        ).max_charge_credits

    async def _resolve_mission_pricing_policy(
        self,
        *,
        mission_policy_id: str,
        workspace_type: str | None,
    ) -> Any | None:
        async with self._client() as client:
            if not hasattr(client, "list_pricing_policies"):
                return None
            try:
                policies = await client.list_pricing_policies(
                    policy_kind="mission",
                    enabled_only=True,
                )
            except Exception:
                return None
        normalized_policy_id = str(mission_policy_id or "").strip()
        normalized_workspace = str(workspace_type or "").strip()
        workspace_default = None
        global_default = None
        for policy in policies:
            config = self._pricing_policy_config(policy)
            policy_mission = str(config.get("mission_policy_id") or "").strip()
            policy_workspace = str(config.get("workspace_type") or "").strip()
            if policy_mission == normalized_policy_id:
                if not policy_workspace or policy_workspace == normalized_workspace:
                    return policy
                continue
            if policy_mission:
                continue
            if policy_workspace == normalized_workspace and workspace_default is None:
                workspace_default = policy
                continue
            if not policy_workspace and global_default is None:
                global_default = policy
        return workspace_default or global_default

    async def consume_for_sandbox_operation(
        self,
        *,
        user_id: str,
        operation: str,
        mission_id: str,
        mission_item_seq: int,
        workspace_id: str | None = None,
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
        tx_metadata["mission_id"] = mission_id
        tx_metadata["mission_item_seq"] = mission_item_seq
        if metadata:
            tx_metadata.update(metadata)
        tx_metadata["idempotency_key"] = (
            f"sandbox_operation_billing:{mission_id}:{mission_item_seq}:{normalized_operation}"
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
                    mission_id=mission_id,
                    operation_key=f"sandbox.{normalized_operation}",
                    workspace_id=workspace_id,
                    task_id=None,
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

    async def reserve_for_mission(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        mission_id: str,
        estimated_credits: int,
        expires_at: Any | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Reserve credits before launching a long-running feature execution."""
        key = idempotency_key or f"mission:{mission_id}"
        async with self._client() as client:
            return await client.create_credit_reservation(
                CreditReservationCreatePayload(
                    user_id=user_id,
                    scope="mission",
                    reserved_credits=max(int(estimated_credits or 0), 0),
                    idempotency_key=key,
                    workspace_id=workspace_id,
                    mission_id=mission_id,
                    metadata=dict(metadata or {}),
                    expires_at=expires_at,
                )
            )

    async def settle_mission_reservation(
        self,
        *,
        reservation_id: str,
        settled_credits: int,
        mission_policy_id: str,
        mission_id: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, Any | None]:
        """Settle a Mission reservation into the credit ledger."""
        async with self._client() as client:
            return await client.settle_credit_reservation(
                reservation_id,
                CreditReservationSettlePayload(
                    settled_credits=max(int(settled_credits or 0), 0),
                    description=description or f"{mission_policy_id} 任务结算",
                    transaction_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                    mission_policy_id=mission_policy_id,
                    mission_id=mission_id,
                    metadata=dict(metadata or {}),
                ),
            )

    async def reserve_for_sandbox_operation(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        mission_id: str,
        mission_item_seq: int,
        operation: str,
        estimated_credits: int,
        expires_at: Any | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Reserve credits before acquiring sandbox compute resources."""
        normalized_operation = self._normalize_sandbox_operation(operation)
        key = idempotency_key or (
            f"sandbox_operation:{mission_id}:{mission_item_seq}:{normalized_operation}"
        )
        async with self._client() as client:
            return await client.create_credit_reservation(
                CreditReservationCreatePayload(
                    user_id=user_id,
                    scope="sandbox_operation",
                    reserved_credits=max(int(estimated_credits or 0), 0),
                    idempotency_key=key,
                    workspace_id=workspace_id,
                    mission_id=mission_id,
                    mission_item_seq=mission_item_seq,
                    metadata={"operation": normalized_operation, **dict(metadata or {})},
                    expires_at=expires_at,
                )
            )

    async def estimate_sandbox_reservation_credits(
        self,
        *,
        operation: str,
        sandbox_policy: dict[str, Any] | None = None,
    ) -> int:
        """Return conservative sandbox reservation credits."""
        normalized_operation = self._normalize_sandbox_operation(operation)
        policy = dict(sandbox_policy or {})
        configured_max = self._policy_int(policy, "max_charge_credits", 0)
        if configured_max > 0:
            return configured_max
        estimated = calculate_sandbox_estimate(
            policy,
            operation=normalized_operation,
            duration_seconds=self._policy_int(policy, "minimum_billable_seconds", 0),
        ).credits
        if estimated > 0:
            return estimated
        return self._sandbox_operation_credits(
            self.get_sandbox_billing_policy(),
            normalized_operation,
        )

    async def estimate_sandbox_settlement_credits(
        self,
        *,
        operation: str,
        sandbox_policy: dict[str, Any] | None = None,
        duration_seconds: int = 0,
    ) -> int:
        """Return actual sandbox settlement credits after runtime usage is known."""
        normalized_operation = self._normalize_sandbox_operation(operation)
        estimated = calculate_sandbox_estimate(
            dict(sandbox_policy or {}),
            operation=normalized_operation,
            duration_seconds=duration_seconds,
        ).credits
        if estimated > 0:
            return estimated
        return self._sandbox_operation_credits(
            self.get_sandbox_billing_policy(),
            normalized_operation,
        )

    async def settle_sandbox_reservation(
        self,
        *,
        reservation_id: str,
        settled_credits: int,
        operation: str,
        mission_id: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, Any | None]:
        """Settle a sandbox reservation after runtime usage is known."""
        normalized_operation = self._normalize_sandbox_operation(operation)
        async with self._client() as client:
            return await client.settle_credit_reservation(
                reservation_id,
                CreditReservationSettlePayload(
                    settled_credits=max(int(settled_credits or 0), 0),
                    description=description or self._build_sandbox_operation_description(
                        operation=normalized_operation,
                        credits_charged=max(int(settled_credits or 0), 0),
                    ),
                    transaction_type=CreditTransactionType.WORKFLOW_CONSUME.value,
                    mission_id=mission_id,
                    operation_key=f"sandbox.{normalized_operation}",
                    metadata={"operation": normalized_operation, **dict(metadata or {})},
                ),
            )

    async def release_reservation(
        self,
        reservation_id: str,
        *,
        reason: str | None = None,
    ) -> Any:
        """Release a DataService credit reservation."""
        async with self._client() as client:
            return await client.release_credit_reservation(reservation_id, reason=reason)

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

    def _build_mission_token_description(
        self,
        *,
        mission_policy_id: str,
        total_tokens: int,
        credits_charged: int,
        free_tokens_applied: int,
    ) -> str:
        if credits_charged <= 0:
            if free_tokens_applied > 0:
                return f"{mission_policy_id} 用量记录（免费额度内）"
            return f"{mission_policy_id} 用量记录"
        return f"{mission_policy_id} 扣费 {credits_charged} 积分"

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
