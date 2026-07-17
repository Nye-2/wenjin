"""Atomic authorization and settlement for transient chat turns."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.policies import (
    ChatTurnAuthorizationQuote,
    calculate_chat_turn_authorization,
    calculate_model_usage_credits,
)
from src.contracts.billing import CreditTransactionType, ThreadTurnBillingStatus
from src.contracts.pricing_snapshot import (
    ChatTurnPricingSnapshot,
    freeze_pricing_policy,
)
from src.database.base import generate_uuid
from src.database.models.thread_turn_billing import ThreadTurnBilling
from src.dataservice.common.errors import (
    CreditOverdraftLimitError,
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.conversation.contracts import (
    ConversationMessageCreateCommand,
)
from src.dataservice.domains.conversation.service import (
    DataServiceConversationService,
)
from src.dataservice.domains.credit.repository import CreditRepository
from src.dataservice.domains.pricing.contracts import (
    GlobalCreditPolicyConfig,
    ModelUsagePolicyConfig,
)
from src.dataservice.domains.pricing.resolver import CanonicalPricingResolver
from src.dataservice.domains.thread_turn_billing.repository import (
    ThreadTurnBillingRepository,
)
from src.dataservice_client.contracts.conversation import ConversationMessagePayload
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnAuthorizationResultPayload,
    ThreadTurnAuthorizePayload,
    ThreadTurnBillingPayload,
    ThreadTurnCompletePayload,
    ThreadTurnCompletionResultPayload,
    ThreadTurnReconcilePayload,
    ThreadTurnReconcileResultPayload,
    ThreadTurnReleaseByKeyPayload,
    ThreadTurnReleaseByKeyResultPayload,
    ThreadTurnReleasePayload,
    ThreadTurnRollbackPayload,
    ThreadTurnRollbackResultPayload,
)


class ThreadTurnBillingService:
    """Own the user lock, conversation write, and credit ledger transaction."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = False) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ThreadTurnBillingRepository(session)
        self.credits = CreditRepository(session)
        self.conversation = DataServiceConversationService(
            session,
            autocommit=False,
        )
        self.pricing = CanonicalPricingResolver(session)

    async def authorize(
        self,
        command: ThreadTurnAuthorizePayload,
    ) -> ThreadTurnAuthorizationResultPayload:
        message_command = command.user_message
        user = await self.credits.get_user_for_update(message_command.user_id)
        if user is None:
            raise DataServiceNotFoundError("User not found")

        existing = await self.repository.get_by_idempotency_key_for_update(
            command.idempotency_key
        )
        if existing is not None:
            return await self._replay_authorization(existing, command)

        thread = await self.conversation.repository.get_owned_thread(
            thread_id=message_command.thread_id,
            user_id=message_command.user_id,
        )
        if thread is None:
            raise DataServiceNotFoundError("Thread not found")
        if (
            message_command.workspace_id is not None
            and str(thread.workspace_id or "") != message_command.workspace_id
        ):
            raise DataServiceConflictError(
                "Thread workspace does not match the chat-turn request"
            )
        if str(thread.model or "") != command.model_id:
            raise DataServiceConflictError(
                "Thread model does not match the chat-turn authorization"
            )

        model_policy = await self.pricing.resolve_model_usage(command.model_id)
        global_policy = await self.pricing.resolve_global_credit()
        model_config = ModelUsagePolicyConfig.model_validate(
            dict(model_policy.config_json or {})
        )
        global_config = (
            GlobalCreditPolicyConfig.model_validate(
                dict(global_policy.config_json or {})
            )
            if global_policy is not None
            else None
        )

        consumed_tokens = int(user.thread_consumed_tokens or 0)
        reserved_tokens = int(user.reserved_thread_free_tokens or 0)
        quote = calculate_chat_turn_authorization(
            model_policy=model_config.model_dump(mode="python"),
            global_policy=(
                global_config.model_dump(mode="python")
                if global_config is not None
                else None
            ),
            historical_tokens=consumed_tokens,
            reserved_free_tokens=reserved_tokens,
        )
        available_with_overdraft = (
            int(user.credits or 0)
            - int(user.reserved_credits or 0)
            + model_config.max_overdraft_credits
        )
        if quote.credit_hold > available_with_overdraft:
            raise CreditOverdraftLimitError(
                "insufficient capacity for a bounded chat-turn authorization"
            )

        billing_id = generate_uuid()
        metadata = dict(message_command.metadata)
        metadata["billing_authorization_id"] = billing_id
        message = await self.conversation.append_message(
            ConversationMessageCreateCommand.model_validate(
                {
                    **message_command.model_dump(mode="python"),
                    "metadata": metadata,
                }
            )
        )
        now = await self.repository.database_now()
        expires_at = _aware(now) + timedelta(
            seconds=model_config.chat_turn_authorization_ttl_seconds
        )
        user.reserved_thread_free_tokens = reserved_tokens + quote.free_token_hold
        user.reserved_credits = int(user.reserved_credits or 0) + quote.credit_hold
        billing = self.repository.create(
            {
                "id": billing_id,
                "user_id": message_command.user_id,
                "workspace_id": message_command.workspace_id,
                "thread_id": message_command.thread_id,
                "user_message_id": str(message.id),
                "idempotency_key": command.idempotency_key,
                "request_hash": _request_hash(command),
                "model_id": command.model_id,
                "status": ThreadTurnBillingStatus.AUTHORIZED.value,
                "reserved_credits": quote.credit_hold,
                "reserved_free_tokens": quote.free_token_hold,
                "settled_credits": 0,
                "pricing_snapshot_json": _pricing_snapshot(
                    model_policy=model_policy,
                    model_config=model_config,
                    global_policy=global_policy,
                    global_config=global_config,
                    authorization_quote=quote,
                ),
                "expires_at": expires_at,
            }
        )
        await self._finish(billing)
        return ThreadTurnAuthorizationResultPayload(
            billing=_billing_payload(billing),
            user_message=await self._message_payload(str(message.id)),
            assistant_message=None,
            created=True,
        )

    async def complete(
        self,
        billing_id: str,
        command: ThreadTurnCompletePayload,
    ) -> ThreadTurnCompletionResultPayload:
        user = await self.credits.get_user_for_update(command.user_id)
        if user is None:
            raise DataServiceNotFoundError("User not found")
        billing = await self.repository.get_for_update(billing_id)
        if billing is None or billing.user_id != command.user_id:
            raise DataServiceNotFoundError("Chat-turn authorization not found")
        if billing.status == ThreadTurnBillingStatus.SETTLED.value:
            return await self._replay_completion(billing)
        if billing.status != ThreadTurnBillingStatus.AUTHORIZED.value:
            raise DataServiceConflictError(
                "Chat-turn authorization is no longer active",
                detail={"status": billing.status},
            )
        completion_time = _aware(await self.repository.database_now())
        if _aware(billing.expires_at) <= completion_time:
            raise DataServiceConflictError(
                "Chat-turn authorization has expired",
                detail={"status": ThreadTurnBillingStatus.EXPIRED.value},
            )

        assistant = command.assistant_message
        if (
            assistant.thread_id != billing.thread_id
            or assistant.user_id != billing.user_id
            or assistant.workspace_id != billing.workspace_id
        ):
            raise DataServiceConflictError(
                "Assistant message does not match the chat-turn authorization"
            )

        usage = command.token_usage
        if usage.total_tokens <= 0:
            raise DataServiceValidationError(
                "A completed chat turn requires non-zero model usage"
            )
        try:
            snapshot = ChatTurnPricingSnapshot.model_validate(
                billing.pricing_snapshot_json
            )
            model_config = ModelUsagePolicyConfig.model_validate(
                snapshot.model_policy.config
            )
            global_config = (
                GlobalCreditPolicyConfig.model_validate(
                    snapshot.global_policy.config
                )
                if snapshot.global_policy is not None
                else None
            )
        except ValueError as exc:
            raise DataServiceConflictError(
                "Chat-turn pricing snapshot is invalid"
            ) from exc

        free_tokens_applied = min(
            usage.total_tokens,
            int(billing.reserved_free_tokens or 0),
        )
        billable_tokens = max(usage.total_tokens - free_tokens_applied, 0)
        charge = calculate_model_usage_credits(
            model_policy=model_config,
            global_policy=(
                global_config.model_dump(mode="python")
                if global_config is not None
                else None
            ),
            token_usage=usage.model_dump(mode="python"),
            surface="chat",
            billable_tokens=billable_tokens,
        )
        uncapped_credits = charge.credits_to_charge

        reserved_credits = int(billing.reserved_credits or 0)
        reserved_free_tokens = int(billing.reserved_free_tokens or 0)
        if int(user.reserved_credits or 0) < reserved_credits:
            raise DataServiceConflictError(
                "User credit reservation projection is inconsistent"
            )
        if int(user.reserved_thread_free_tokens or 0) < reserved_free_tokens:
            raise DataServiceConflictError(
                "User free-token reservation projection is inconsistent"
            )
        credits_to_charge = min(uncapped_credits, reserved_credits)

        historical_before = int(user.thread_consumed_tokens or 0)
        historical_after = historical_before + usage.total_tokens
        user.reserved_credits = int(user.reserved_credits or 0) - reserved_credits
        user.reserved_thread_free_tokens = (
            int(user.reserved_thread_free_tokens or 0) - reserved_free_tokens
        )
        user.thread_consumed_tokens = historical_after
        user.credits = int(user.credits or 0) - credits_to_charge
        user.total_credits_spent = (
            int(user.total_credits_spent or 0) + credits_to_charge
        )

        billing_metadata = {
            "type": "thread_token_billing",
            "authorization_id": str(billing.id),
            "token_usage": usage.model_dump(mode="json"),
            "model_name": billing.model_id,
            "free_tokens_applied": free_tokens_applied,
            "billable_tokens": billable_tokens,
            "credits_charged": credits_to_charge,
            "uncapped_credits": uncapped_credits,
            "charge_capped": uncapped_credits > credits_to_charge,
            "authorization_credit_limit": reserved_credits,
            "historical_tokens_before": historical_before,
            "historical_tokens_after": historical_after,
            "balance_after": int(user.credits),
            "charged": credits_to_charge > 0,
            "pricing": {
                "model_policy_id": snapshot.model_policy.id,
                "model_policy_version": snapshot.model_policy.version,
                "global_policy_id": (
                    snapshot.global_policy.id
                    if snapshot.global_policy is not None
                    else None
                ),
            },
        }
        transaction = self.credits.create_credit_transaction(
            {
                "user_id": billing.user_id,
                "transaction_type": CreditTransactionType.THREAD_TOKEN_CONSUME,
                "amount": -credits_to_charge,
                "balance_after": user.credits,
                "description": "Chat turn usage settlement",
                "workspace_id": billing.workspace_id,
                "idempotency_key": f"thread-turn:{billing.id}",
                "tx_metadata": billing_metadata,
            }
        )
        await self.session.flush([transaction])
        billing_metadata["transaction_id"] = str(transaction.id)

        assistant_metadata = dict(assistant.metadata)
        assistant_metadata["billing"] = billing_metadata
        message = await self.conversation.append_message(
            ConversationMessageCreateCommand.model_validate(
                {
                    **assistant.model_dump(mode="python"),
                    "metadata": assistant_metadata,
                }
            )
        )
        now = completion_time
        billing.status = ThreadTurnBillingStatus.SETTLED.value
        billing.assistant_message_id = str(message.id)
        billing.transaction_id = str(transaction.id)
        billing.settled_credits = credits_to_charge
        billing.input_tokens = usage.input_tokens
        billing.cached_input_tokens = usage.cached_input_tokens
        billing.output_tokens = usage.output_tokens
        billing.reasoning_tokens = usage.reasoning_tokens
        billing.total_tokens = usage.total_tokens
        billing.settled_at = now
        await self._finish(billing)
        return ThreadTurnCompletionResultPayload(
            billing=_billing_payload(billing),
            assistant_message=await self._message_payload(str(message.id)),
            billing_metadata=billing_metadata,
        )

    async def release(
        self,
        billing_id: str,
        command: ThreadTurnReleasePayload,
        *,
        expired: bool = False,
    ) -> ThreadTurnBillingPayload:
        user = await self.credits.get_user_for_update(command.user_id)
        if user is None:
            raise DataServiceNotFoundError("User not found")
        billing = await self.repository.get_for_update(billing_id)
        if billing is None or billing.user_id != command.user_id:
            raise DataServiceNotFoundError("Chat-turn authorization not found")
        await self._release_locked(
            user=user,
            billing=billing,
            reason=command.reason,
            expired=expired,
        )
        await self._finish(billing)
        return _billing_payload(billing)

    async def release_by_idempotency_key(
        self,
        command: ThreadTurnReleaseByKeyPayload,
    ) -> ThreadTurnReleaseByKeyResultPayload:
        """Compensate an authorization whose response was lost.

        The user row is locked before the idempotency lookup, matching the
        authorization lock order. A concurrent authorization for the same
        user therefore commits or rolls back before this command observes it.
        """
        user = await self.credits.get_user_for_update(command.user_id)
        if user is None:
            raise DataServiceNotFoundError("User not found")
        billing = await self.repository.get_by_idempotency_key_for_update(
            command.idempotency_key
        )
        if billing is None or billing.user_id != command.user_id:
            return ThreadTurnReleaseByKeyResultPayload()
        await self._release_locked(
            user=user,
            billing=billing,
            reason=command.reason,
            expired=False,
        )
        await self._finish(billing)
        return ThreadTurnReleaseByKeyResultPayload(
            billing=_billing_payload(billing)
        )

    async def rollback(
        self,
        billing_id: str,
        command: ThreadTurnRollbackPayload,
    ) -> ThreadTurnRollbackResultPayload:
        user = await self.credits.get_user_for_update(command.user_id)
        if user is None:
            raise DataServiceNotFoundError("User not found")
        billing = await self.repository.get_for_update(billing_id)
        if billing is None or billing.user_id != command.user_id:
            raise DataServiceNotFoundError("Chat-turn authorization not found")
        if billing.status == ThreadTurnBillingStatus.SETTLED.value:
            raise DataServiceConflictError("A settled chat turn cannot be rolled back")

        await self._release_locked(
            user=user,
            billing=billing,
            reason=command.reason,
            expired=False,
        )
        message_id = str(billing.user_message_id or "")
        message_rolled_back = False
        if message_id:
            billing.user_message_id = None
            await self.session.flush([billing])
            message_rolled_back = await self.conversation.delete_trailing_user_message(
                thread_id=billing.thread_id,
                user_id=billing.user_id,
                expected_message_id=message_id,
            )
            if not message_rolled_back:
                billing.user_message_id = message_id
        await self._finish(billing)
        return ThreadTurnRollbackResultPayload(
            billing=_billing_payload(billing),
            message_rolled_back=message_rolled_back,
        )

    async def reconcile_expired(
        self,
        command: ThreadTurnReconcilePayload,
    ) -> ThreadTurnReconcileResultPayload:
        now = _aware(command.now or await self.repository.database_now())
        candidates = await self.repository.list_expired_authorizations(
            now=now,
            limit=command.limit,
        )
        expired_ids: list[str] = []
        candidates_by_user: dict[str, list[str]] = defaultdict(list)
        for billing_id, user_id in candidates:
            candidates_by_user[user_id].append(billing_id)
        for user_id in sorted(candidates_by_user):
            user = await self.credits.get_user_for_update(user_id)
            if user is None:
                continue
            billings = await self.repository.list_expired_for_user_for_update(
                user_id=user_id,
                billing_ids=candidates_by_user[user_id],
                now=now,
            )
            for billing in billings:
                await self._release_locked(
                    user=user,
                    billing=billing,
                    reason="authorization expired before completion",
                    expired=True,
                    released_at=now,
                )
                expired_ids.append(str(billing.id))
        await self._finish()
        return ThreadTurnReconcileResultPayload(
            expired_billing_ids=expired_ids
        )

    async def _release_locked(
        self,
        *,
        user: Any,
        billing: ThreadTurnBilling,
        reason: str,
        expired: bool,
        released_at: datetime | None = None,
    ) -> None:
        if billing.status != ThreadTurnBillingStatus.AUTHORIZED.value:
            return
        reserved_credits = int(billing.reserved_credits or 0)
        reserved_tokens = int(billing.reserved_free_tokens or 0)
        if (
            int(user.reserved_credits or 0) < reserved_credits
            or int(user.reserved_thread_free_tokens or 0) < reserved_tokens
        ):
            raise DataServiceConflictError(
                "User chat-turn reservation projection is inconsistent"
            )
        user.reserved_credits = int(user.reserved_credits or 0) - reserved_credits
        user.reserved_thread_free_tokens = (
            int(user.reserved_thread_free_tokens or 0) - reserved_tokens
        )
        billing.status = (
            ThreadTurnBillingStatus.EXPIRED.value
            if expired
            else ThreadTurnBillingStatus.RELEASED.value
        )
        billing.release_reason = reason
        billing.released_at = _aware(
            released_at or await self.repository.database_now()
        )

    async def delete_thread(self, *, thread_id: str, user_id: str) -> bool:
        """Release active authorizations and delete an owned thread atomically."""
        user = await self.credits.get_user_for_update(user_id)
        if user is None:
            return False
        await self.conversation.repository.lock_thread(thread_id)
        thread = await self.conversation.repository.get_owned_thread(
            thread_id=thread_id,
            user_id=user_id,
        )
        if thread is None:
            return False
        released_at = _aware(await self.repository.database_now())
        for billing in await self.repository.list_authorized_for_thread_for_update(
            thread_id
        ):
            await self._release_locked(
                user=user,
                billing=billing,
                reason="thread deleted by user",
                expired=False,
                released_at=released_at,
            )
        await self.conversation.repository.delete_thread(thread)
        await self._finish()
        return True

    async def _replay_authorization(
        self,
        billing: ThreadTurnBilling,
        command: ThreadTurnAuthorizePayload,
    ) -> ThreadTurnAuthorizationResultPayload:
        if billing.request_hash != _request_hash(command):
            raise DataServiceConflictError(
                "Chat-turn idempotency key was reused for a different request"
            )
        if billing.status in {
            ThreadTurnBillingStatus.RELEASED.value,
            ThreadTurnBillingStatus.EXPIRED.value,
        }:
            raise DataServiceConflictError(
                "Chat-turn authorization is no longer active",
                detail={"status": billing.status},
            )
        message = (
            await self._message_payload(str(billing.user_message_id))
            if billing.user_message_id
            else None
        )
        assistant = (
            await self._message_payload(str(billing.assistant_message_id))
            if billing.status == ThreadTurnBillingStatus.SETTLED.value
            and billing.assistant_message_id
            else None
        )
        if billing.status == ThreadTurnBillingStatus.AUTHORIZED.value and message is None:
            raise DataServiceConflictError(
                "Active chat-turn authorization has no user message"
            )
        return ThreadTurnAuthorizationResultPayload(
            billing=_billing_payload(billing),
            user_message=message,
            assistant_message=assistant,
            created=False,
        )

    async def _replay_completion(
        self,
        billing: ThreadTurnBilling,
    ) -> ThreadTurnCompletionResultPayload:
        if not billing.assistant_message_id or not billing.transaction_id:
            raise DataServiceConflictError(
                "Settled chat-turn authorization is incomplete"
            )
        message = await self._message_payload(billing.assistant_message_id)
        metadata = dict(message.metadata_json.get("billing") or {})
        return ThreadTurnCompletionResultPayload(
            billing=_billing_payload(billing),
            assistant_message=message,
            billing_metadata=metadata,
        )

    async def _message_payload(self, message_id: str) -> ConversationMessagePayload:
        record = await self.conversation.get_message_record(message_id)
        if record is None:
            raise DataServiceConflictError(
                "Chat-turn billing references a missing conversation message"
            )
        return ConversationMessagePayload.model_validate(
            record.model_dump(mode="python")
        )

    async def _finish(self, *refresh_records: Any) -> None:
        await self.session.flush()
        for record in refresh_records:
            await self.session.refresh(record)
        if self.autocommit:
            await self.session.commit()


def _pricing_snapshot(
    *,
    model_policy: Any,
    model_config: ModelUsagePolicyConfig,
    global_policy: Any | None,
    global_config: GlobalCreditPolicyConfig | None,
    authorization_quote: ChatTurnAuthorizationQuote,
) -> dict[str, Any]:
    return ChatTurnPricingSnapshot(
        authorization=authorization_quote.as_dict(),
        model_policy=freeze_pricing_policy(
            model_policy,
            config=model_config,
        ),
        global_policy=(
            freeze_pricing_policy(global_policy, config=global_config)
            if global_policy is not None and global_config is not None
            else None
        ),
    ).model_dump(mode="json")


def _billing_payload(billing: ThreadTurnBilling) -> ThreadTurnBillingPayload:
    return ThreadTurnBillingPayload(
        id=str(billing.id),
        user_id=str(billing.user_id),
        workspace_id=(str(billing.workspace_id) if billing.workspace_id else None),
        thread_id=str(billing.thread_id),
        user_message_id=(str(billing.user_message_id) if billing.user_message_id else None),
        assistant_message_id=(
            str(billing.assistant_message_id)
            if billing.assistant_message_id
            else None
        ),
        idempotency_key=billing.idempotency_key,
        model_id=billing.model_id,
        status=ThreadTurnBillingStatus(billing.status),
        reserved_credits=int(billing.reserved_credits or 0),
        reserved_free_tokens=int(billing.reserved_free_tokens or 0),
        settled_credits=int(billing.settled_credits or 0),
        token_usage={
            "input_tokens": int(billing.input_tokens or 0),
            "cached_input_tokens": int(billing.cached_input_tokens or 0),
            "output_tokens": int(billing.output_tokens or 0),
            "reasoning_tokens": int(billing.reasoning_tokens or 0),
            "total_tokens": int(billing.total_tokens or 0),
        },
        pricing_snapshot=dict(billing.pricing_snapshot_json or {}),
        transaction_id=(str(billing.transaction_id) if billing.transaction_id else None),
        expires_at=_aware(billing.expires_at),
        settled_at=_aware(billing.settled_at) if billing.settled_at else None,
        released_at=_aware(billing.released_at) if billing.released_at else None,
        release_reason=billing.release_reason,
        created_at=_aware(billing.created_at) if billing.created_at else None,
        updated_at=_aware(billing.updated_at) if billing.updated_at else None,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _request_hash(command: ThreadTurnAuthorizePayload) -> str:
    message = command.user_message
    canonical = {
        "model_id": command.model_id,
        "thread_id": message.thread_id,
        "user_id": message.user_id,
        "workspace_id": message.workspace_id,
        "role": message.role,
        "content": message.content,
        "blocks": message.blocks,
        "metadata": message.metadata,
        "source_json": message.source_json,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

__all__ = ["ThreadTurnBillingService"]
