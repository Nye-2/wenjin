"""Typed client for atomic chat-turn billing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

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


class ThreadTurnBillingDataServiceClient:
    def __init__(
        self,
        request: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        self._request = request

    async def authorize(
        self,
        command: ThreadTurnAuthorizePayload,
    ) -> ThreadTurnAuthorizationResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/thread-turn-billings/authorize",
            json=command.model_dump(mode="json"),
        )
        return ThreadTurnAuthorizationResultPayload.model_validate(
            payload["data"]
        )

    async def complete(
        self,
        billing_id: str,
        command: ThreadTurnCompletePayload,
    ) -> ThreadTurnCompletionResultPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/thread-turn-billings/{billing_id}/complete",
            json=command.model_dump(mode="json"),
        )
        return ThreadTurnCompletionResultPayload.model_validate(payload["data"])

    async def release(
        self,
        billing_id: str,
        command: ThreadTurnReleasePayload,
    ) -> ThreadTurnBillingPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/thread-turn-billings/{billing_id}/release",
            json=command.model_dump(mode="json"),
        )
        return ThreadTurnBillingPayload.model_validate(payload["data"])

    async def release_by_idempotency_key(
        self,
        command: ThreadTurnReleaseByKeyPayload,
    ) -> ThreadTurnReleaseByKeyResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/thread-turn-billings/release-by-idempotency-key",
            json=command.model_dump(mode="json"),
        )
        return ThreadTurnReleaseByKeyResultPayload.model_validate(
            payload["data"]
        )

    async def reconcile_expired(
        self,
        command: ThreadTurnReconcilePayload | None = None,
    ) -> ThreadTurnReconcileResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/thread-turn-billings/reconcile-expired",
            json=(command or ThreadTurnReconcilePayload()).model_dump(
                mode="json"
            ),
        )
        return ThreadTurnReconcileResultPayload.model_validate(payload["data"])

    async def rollback(
        self,
        billing_id: str,
        command: ThreadTurnRollbackPayload,
    ) -> ThreadTurnRollbackResultPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/thread-turn-billings/{billing_id}/rollback",
            json=command.model_dump(mode="json"),
        )
        return ThreadTurnRollbackResultPayload.model_validate(payload["data"])


__all__ = ["ThreadTurnBillingDataServiceClient"]
