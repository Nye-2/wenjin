"""Credit contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreditGrantRulePayload(BaseModel):
    id: str
    name: str
    rule_type: str
    enabled: bool
    amount: int
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    last_triggered_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_admin_id: str | None = None


class CreditTransactionPayload(BaseModel):
    id: str
    user_id: str
    transaction_type: str
    amount: int
    balance_after: int
    description: str | None = None
    feature_id: str | None = None
    workspace_id: str | None = None
    task_id: str | None = None
    admin_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class CreditReservationPayload(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    execution_id: str | None = None
    node_id: str | None = None
    scope: str
    status: str
    reserved_credits: int
    settled_credits: int = 0
    transaction_id: str | None = None
    idempotency_key: str
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreditRedeemCodePayload(BaseModel):
    id: str
    code: str
    amount: int
    max_uses: int
    use_count: int
    per_user_limit: int
    expires_at: datetime | None = None
    valid_from: datetime | None = None
    enabled: bool
    batch_id: str | None = None
    description: str | None = None
    created_at: datetime | None = None
    created_by_admin_id: str | None = None


class CreditReferralPayload(BaseModel):
    id: str
    referrer_user_id: str
    referee_user_id: str
    referrer_credited_at: datetime | None = None
    referee_credited_at: datetime | None = None
    referee_first_task_at: datetime | None = None
    created_at: datetime | None = None


class CreditHistoryPayload(BaseModel):
    transactions: list[CreditTransactionPayload] = Field(default_factory=list)
    total: int


class CreditSummaryPayload(BaseModel):
    credits: int
    reserved_credits: int = 0
    spendable_credits: int = 0
    total_earned: int
    total_spent: int


class CreditAdminSummaryPayload(BaseModel):
    total_issued: int
    total_spent: int
    in_circulation: int
    manual_deductions: int
    overdraft_users: int
    overdraft_credits_total: int
    total_transactions: int


class CreditTokenUsagePayload(BaseModel):
    total_tokens: int
    transactions: int
    users: int


class CreditConsumptionStatsPayload(BaseModel):
    kpis: dict[str, int] = Field(default_factory=dict)
    credit_series: list[dict[str, Any]] = Field(default_factory=list)


class CreditGrantRuleCreatePayload(BaseModel):
    name: str
    rule_type: str
    amount: int
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    admin_id: str


class CreditGrantRuleUpdatePayload(BaseModel):
    name: str
    amount: int
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class CreditConsumptionCreatePayload(BaseModel):
    user_id: str
    transaction_type: str
    amount: int
    description: str
    feature_id: str | None = None
    workspace_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreditReservationCreatePayload(BaseModel):
    user_id: str
    scope: str
    reserved_credits: int
    idempotency_key: str
    workspace_id: str | None = None
    execution_id: str | None = None
    node_id: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreditReservationSettlePayload(BaseModel):
    settled_credits: int
    description: str
    transaction_type: str = "workflow_consume"
    feature_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreditReservationReleasePayload(BaseModel):
    reason: str | None = None


class CreditRefundPayload(BaseModel):
    user_id: str
    original_transaction_id: str
    reason: str
    task_id: str | None = None


class CreditAdminAdjustPayload(BaseModel):
    admin_id: str | None = None
    target_user_id: str
    amount: int
    transaction_type: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreditRedeemCodeCreatePayload(BaseModel):
    code: str
    amount: int
    max_uses: int
    per_user_limit: int
    expires_at: datetime | None = None
    description: str | None = None
    admin_id: str
    batch_id: str


class CreditRedeemPayload(BaseModel):
    code: str
    user_id: str


class CreditReferralCreatePayload(BaseModel):
    referrer_user_id: str
    referee_user_id: str


class CreditPeriodicGrantProcessPayload(BaseModel):
    now: datetime | None = None


class CreditPeriodicGrantSummaryPayload(BaseModel):
    rules_evaluated: int
    rules_fired: int
    users_granted: int
