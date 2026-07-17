"""Canonical financial state and ledger enums shared across boundaries."""

from enum import StrEnum


class CreditTransactionType(StrEnum):
    """Supported entries in the credit ledger."""

    ADMIN_GRANT = "admin_grant"
    ADMIN_DEDUCT = "admin_deduct"
    WORKFLOW_CONSUME = "workflow_consume"
    THREAD_TOKEN_CONSUME = "thread_token_consume"
    REGISTRATION_BONUS = "registration_bonus"
    REFERRAL_BONUS = "referral_bonus"
    REDEEM_CODE = "redeem_code"


class ThreadTurnBillingStatus(StrEnum):
    """Lifecycle states for one atomic chat-turn authorization."""

    AUTHORIZED = "authorized"
    SETTLED = "settled"
    RELEASED = "released"
    EXPIRED = "expired"


__all__ = ["CreditTransactionType", "ThreadTurnBillingStatus"]
