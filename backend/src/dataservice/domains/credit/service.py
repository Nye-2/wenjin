"""Credit command/query service."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from croniter import croniter
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.billing import CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRuleType
from src.database.models.credit_reservation import CreditReservationStatus
from src.dataservice.common.errors import (
    CreditOverdraftLimitError,
    DataServiceValidationError,
)
from src.dataservice.domains.credit.repository import CreditRepository

_PERIODIC_GRANT_CURSOR_VERSION = 1
_PERIODIC_GRANT_CURSOR_MAX_LENGTH = 2048
_PERIODIC_GRANT_MAX_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class _PeriodicRuleCursor:
    scan_started_at: datetime
    after_rule_id: str | None


@dataclass(frozen=True, slots=True)
class _PeriodicUserCursor:
    scan_started_at: datetime
    rule_id: str
    occurrence: datetime
    amount: int
    active_within_days: int | None
    role: str | None
    after_user_id: str | None


_PeriodicCursor = _PeriodicRuleCursor | _PeriodicUserCursor


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cursor_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("cursor timestamp is required")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("cursor timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _encode_periodic_cursor(cursor: _PeriodicCursor) -> str:
    if isinstance(cursor, _PeriodicRuleCursor):
        payload: dict[str, Any] = {
            "after_rule_id": cursor.after_rule_id,
            "kind": "rule",
            "scan_started_at": cursor.scan_started_at.isoformat(),
            "version": _PERIODIC_GRANT_CURSOR_VERSION,
        }
    else:
        payload = {
            "active_within_days": cursor.active_within_days,
            "after_user_id": cursor.after_user_id,
            "amount": cursor.amount,
            "kind": "users",
            "occurrence": cursor.occurrence.isoformat(),
            "role": cursor.role,
            "rule_id": cursor.rule_id,
            "scan_started_at": cursor.scan_started_at.isoformat(),
            "version": _PERIODIC_GRANT_CURSOR_VERSION,
        }
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_periodic_cursor(cursor: str) -> _PeriodicCursor:
    try:
        if not cursor or len(cursor) > _PERIODIC_GRANT_CURSOR_MAX_LENGTH:
            raise ValueError("cursor length is invalid")
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            raise ValueError("cursor payload must be an object")
        if payload.get("version") != _PERIODIC_GRANT_CURSOR_VERSION:
            raise ValueError("unsupported cursor version")

        kind = payload.get("kind")
        if kind == "rule":
            if set(payload) != {
                "after_rule_id",
                "kind",
                "scan_started_at",
                "version",
            }:
                raise ValueError("invalid rule cursor shape")
            after_rule_id = payload["after_rule_id"]
            if after_rule_id is not None and (
                not isinstance(after_rule_id, str) or not after_rule_id
            ):
                raise ValueError("invalid rule cursor position")
            return _PeriodicRuleCursor(
                scan_started_at=_cursor_datetime(payload["scan_started_at"]),
                after_rule_id=after_rule_id,
            )

        if kind != "users" or set(payload) != {
            "active_within_days",
            "after_user_id",
            "amount",
            "kind",
            "occurrence",
            "role",
            "rule_id",
            "scan_started_at",
            "version",
        }:
            raise ValueError("invalid user cursor shape")
        rule_id = payload["rule_id"]
        after_user_id = payload["after_user_id"]
        amount = payload["amount"]
        active_within_days = payload["active_within_days"]
        role = payload["role"]
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("invalid cursor rule id")
        if not isinstance(after_user_id, str) or not after_user_id:
            raise ValueError("invalid user cursor position")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError("invalid periodic grant amount")
        if active_within_days is not None and (
            isinstance(active_within_days, bool)
            or not isinstance(active_within_days, int)
            or not 0 <= active_within_days <= 36_500
        ):
            raise ValueError("invalid active user window")
        if role not in {None, "user", "admin"}:
            raise ValueError("invalid periodic grant role")
        scan_started_at = _cursor_datetime(payload["scan_started_at"])
        occurrence = _cursor_datetime(payload["occurrence"])
        if occurrence > scan_started_at:
            raise ValueError("periodic occurrence is after scan start")
        return _PeriodicUserCursor(
            scan_started_at=scan_started_at,
            rule_id=rule_id,
            occurrence=occurrence,
            amount=amount,
            active_within_days=active_within_days,
            role=role,
            after_user_id=after_user_id,
        )
    except (
        binascii.Error,
        json.JSONDecodeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise DataServiceValidationError(
            "Invalid periodic credit grant cursor"
        ) from exc


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
        credits = int(user.credits)
        reserved_credits = max(int(user.reserved_credits or 0), 0)
        return {
            "credits": credits,
            "reserved_credits": reserved_credits,
            "spendable_credits": credits - reserved_credits,
            "thread_consumed_tokens": int(user.thread_consumed_tokens or 0),
            "reserved_thread_free_tokens": int(user.reserved_thread_free_tokens or 0),
            "total_earned": int(user.total_credits_earned),
            "total_spent": int(user.total_credits_spent),
        }

    async def get_admin_credit_summary(self) -> dict[str, int]:
        return await self.repository.get_admin_credit_summary()

    async def get_thread_token_usage_summary(self) -> dict[str, int]:
        return await self.repository.get_thread_token_usage_summary()

    async def aggregate_credit_consumption_stats(
        self,
        *,
        since: datetime,
        granularity: str,
    ) -> dict[str, Any]:
        inflow_types = {
            CreditTransactionType.ADMIN_GRANT,
            CreditTransactionType.REGISTRATION_BONUS,
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
            "credit_series": [series_by_bucket[key] for key in sorted(series_by_bucket)],
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

    async def apply_registration_bonus_from_rule(self, *, user_id: str, rule: Any) -> Any:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("user not found")
        amount = int(rule.amount)
        if amount <= 0:
            raise DataServiceValidationError(
                "registration bonus rule amount must be positive"
            )
        idempotency_key = f"registration-bonus:{rule.id}"
        existing = await self.repository.find_credit_transaction_by_idempotency_key(
            user_id=user_id,
            transaction_type=CreditTransactionType.REGISTRATION_BONUS,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing
        user.credits = int(user.credits or 0) + amount
        user.total_credits_earned = int(user.total_credits_earned or 0) + amount
        tx = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": CreditTransactionType.REGISTRATION_BONUS,
                "amount": amount,
                "balance_after": user.credits,
                "description": f"注册奖励 (rule {str(rule.id)[:8]}***)",
                "idempotency_key": idempotency_key,
            }
        )
        await self._finish(tx)
        return tx

    async def process_periodic_grant_page(
        self,
        *,
        now: datetime | None = None,
        cursor: str | None = None,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Process one bounded periodic-grant page and return its opaque cursor."""
        if (
            isinstance(batch_size, bool)
            or not 1 <= int(batch_size) <= _PERIODIC_GRANT_MAX_BATCH_SIZE
        ):
            raise DataServiceValidationError(
                f"batch_size must be between 1 and {_PERIODIC_GRANT_MAX_BATCH_SIZE}"
            )
        if cursor is not None and now is not None:
            raise DataServiceValidationError(
                "now may only be supplied when starting a periodic grant scan"
            )

        state: _PeriodicCursor
        if cursor is None:
            state = _PeriodicRuleCursor(
                scan_started_at=_as_utc(
                    now or await self.repository.database_now()
                ),
                after_rule_id=None,
            )
        else:
            state = _decode_periodic_cursor(cursor)

        if isinstance(state, _PeriodicRuleCursor):
            result = await self._process_periodic_rule_cursor(
                state=state,
                batch_size=int(batch_size),
            )
        else:
            result = await self._process_periodic_user_cursor(
                state=state,
                batch_size=int(batch_size),
            )
        await self._finish()
        return result

    async def _process_periodic_rule_cursor(
        self,
        *,
        state: _PeriodicRuleCursor,
        batch_size: int,
    ) -> dict[str, Any]:
        rule = await self.repository.get_next_enabled_grant_rule_for_update(
            CreditGrantRuleType.PERIODIC,
            after_rule_id=state.after_rule_id,
            created_through=state.scan_started_at,
        )
        if rule is None:
            return {
                "rules_evaluated": 0,
                "rules_fired": 0,
                "users_scanned": 0,
                "users_granted": 0,
                "next_cursor": None,
            }

        next_rule_cursor = _encode_periodic_cursor(
            _PeriodicRuleCursor(
                scan_started_at=state.scan_started_at,
                after_rule_id=str(rule.id),
            )
        )
        snapshot = self._periodic_rule_snapshot(
            rule=rule,
            scan_started_at=state.scan_started_at,
        )
        if snapshot is None:
            return self._periodic_rule_scan_result(next_rule_cursor)
        occurrence, amount, active_within_days, role = snapshot

        return await self._process_periodic_user_cursor(
            state=_PeriodicUserCursor(
                scan_started_at=state.scan_started_at,
                rule_id=str(rule.id),
                occurrence=occurrence,
                amount=amount,
                active_within_days=active_within_days,
                role=role,
                after_user_id=None,
            ),
            batch_size=batch_size,
            rule=rule,
            rules_evaluated=1,
            rules_fired=1,
        )

    @staticmethod
    def _periodic_rule_scan_result(next_cursor: str) -> dict[str, Any]:
        return {
            "rules_evaluated": 1,
            "rules_fired": 0,
            "users_scanned": 0,
            "users_granted": 0,
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _periodic_rule_snapshot(
        *,
        rule: Any,
        scan_started_at: datetime,
    ) -> tuple[datetime, int, int | None, str | None] | None:
        if not bool(rule.enabled):
            return None
        config = rule.config if isinstance(rule.config, dict) else {}
        cron_expr = config.get("cron")
        if not isinstance(cron_expr, str) or not cron_expr:
            return None
        base = rule.last_triggered_at or (scan_started_at - timedelta(days=30))
        try:
            occurrence = _as_utc(croniter(cron_expr, base).get_next(datetime))
            amount = int(rule.amount)
            target_filter = (
                config.get("target_filter", {})
                if isinstance(config.get("target_filter", {}), dict)
                else {}
            )
            raw_active_within_days = target_filter.get("active_within_days")
            active_within_days = (
                None
                if raw_active_within_days is None
                else int(raw_active_within_days)
            )
            role = target_filter.get("role")
        except (TypeError, ValueError):
            return None
        if (
            occurrence > scan_started_at
            or amount <= 0
            or (
                active_within_days is not None
                and not 0 <= active_within_days <= 36_500
            )
            or role not in {None, "user", "admin"}
        ):
            return None
        return occurrence, amount, active_within_days, role

    async def _process_periodic_user_cursor(
        self,
        *,
        state: _PeriodicUserCursor,
        batch_size: int,
        rule: Any | None = None,
        rules_evaluated: int = 0,
        rules_fired: int = 0,
    ) -> dict[str, Any]:
        if rule is None:
            rule = await self.repository.get_grant_rule_for_update(state.rule_id)
        if rule is None or rule.rule_type != CreditGrantRuleType.PERIODIC:
            return {
                "rules_evaluated": rules_evaluated,
                "rules_fired": rules_fired,
                "users_scanned": 0,
                "users_granted": 0,
                "next_cursor": _encode_periodic_cursor(
                    _PeriodicRuleCursor(
                        scan_started_at=state.scan_started_at,
                        after_rule_id=state.rule_id,
                    )
                ),
            }

        snapshot = self._periodic_rule_snapshot(
            rule=rule,
            scan_started_at=state.scan_started_at,
        )
        if snapshot is None or snapshot != (
            state.occurrence,
            state.amount,
            state.active_within_days,
            state.role,
        ):
            return {
                "rules_evaluated": rules_evaluated,
                "rules_fired": rules_fired,
                "users_scanned": 0,
                "users_granted": 0,
                "next_cursor": _encode_periodic_cursor(
                    _PeriodicRuleCursor(
                        scan_started_at=state.scan_started_at,
                        after_rule_id=state.rule_id,
                    )
                ),
            }

        active_since = None
        if state.active_within_days is not None:
            active_since = state.scan_started_at - timedelta(
                days=state.active_within_days
            )
        user_ids = await self.repository.list_user_ids_for_periodic_credit_filter(
            active_since=active_since,
            role=state.role,
            created_through=state.scan_started_at,
            after_user_id=state.after_user_id,
            limit=batch_size + 1,
        )
        page_user_ids = user_ids[:batch_size]
        granted = 0
        for user_id in page_user_ids:
            if await self._grant_periodic_user(user_id=user_id, state=state):
                granted += 1

        if len(user_ids) > batch_size:
            next_cursor = _encode_periodic_cursor(
                replace(state, after_user_id=page_user_ids[-1])
            )
        else:
            last_triggered_at = rule.last_triggered_at
            if (
                last_triggered_at is None
                or _as_utc(last_triggered_at) < state.scan_started_at
            ):
                rule.last_triggered_at = state.scan_started_at
            next_cursor = _encode_periodic_cursor(
                _PeriodicRuleCursor(
                    scan_started_at=state.scan_started_at,
                    after_rule_id=state.rule_id,
                )
            )

        return {
            "rules_evaluated": rules_evaluated,
            "rules_fired": rules_fired,
            "users_scanned": len(page_user_ids),
            "users_granted": granted,
            "next_cursor": next_cursor,
        }

    async def _grant_periodic_user(
        self,
        *,
        user_id: str,
        state: _PeriodicUserCursor,
    ) -> bool:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            return False

        occurrence_key = state.occurrence.isoformat()
        idempotency_key = f"periodic-grant:{state.rule_id}:{occurrence_key}"
        existing = await self.repository.find_credit_transaction_by_idempotency_key(
            user_id=user_id,
            transaction_type=CreditTransactionType.ADMIN_GRANT,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return False

        user.credits = int(user.credits or 0) + state.amount
        user.total_credits_earned = (
            int(user.total_credits_earned or 0) + state.amount
        )
        self.repository.create_credit_transaction(
            {
                "user_id": user.id,
                "transaction_type": CreditTransactionType.ADMIN_GRANT,
                "amount": state.amount,
                "balance_after": user.credits,
                "description": f"周期发放（rule {state.rule_id[:8]}***）",
                "idempotency_key": idempotency_key,
                "tx_metadata": {
                    "rule_id": state.rule_id,
                    "scheduled_occurrence": occurrence_key,
                    "scan_started_at": state.scan_started_at.isoformat(),
                    "rule_amount": state.amount,
                },
            }
        )
        return True

    async def create_reservation(
        self,
        *,
        user_id: str,
        reserved_credits: int,
        idempotency_key: str,
        workspace_id: str | None = None,
        mission_id: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Hold credits for long-running billable work without writing a ledger entry."""
        normalized_reserved = max(int(reserved_credits or 0), 0)
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            raise ValueError("Reservation idempotency_key is required")

        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("User not found")

        existing = await self.repository.find_reservation_by_idempotency_key(
            idempotency_key=normalized_key,
        )
        if existing is not None:
            return existing

        spendable_credits = int(user.credits or 0) - int(user.reserved_credits or 0)
        if normalized_reserved > spendable_credits:
            raise CreditOverdraftLimitError("insufficient spendable credits for reservation")

        user.reserved_credits = int(user.reserved_credits or 0) + normalized_reserved
        reservation = self.repository.create_credit_reservation(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "mission_id": mission_id,
                "status": CreditReservationStatus.RESERVED,
                "reserved_credits": normalized_reserved,
                "settled_credits": 0,
                "idempotency_key": normalized_key,
                "expires_at": expires_at,
                "metadata_json": dict(metadata or {}),
            }
        )
        await self._finish(reservation)
        return reservation

    async def settle_reservation(
        self,
        *,
        reservation_id: str,
        settled_credits: int,
        description: str,
        transaction_type: CreditTransactionType = CreditTransactionType.WORKFLOW_CONSUME,
        mission_policy_id: str | None = None,
        mission_id: str | None = None,
        operation_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, Any | None]:
        """Finalize a reservation into a normal credit transaction."""
        reservation = await self.repository.get_reservation_for_update(reservation_id)
        if reservation is None:
            raise ValueError("Credit reservation not found")
        if reservation.status != CreditReservationStatus.RESERVED:
            tx = await self.repository.get_credit_transaction(reservation.transaction_id) if reservation.transaction_id else None
            return reservation, tx

        user = await self.repository.get_user_for_update(reservation.user_id)
        if user is None:
            raise ValueError("User not found")

        reserved_credits = max(int(reservation.reserved_credits or 0), 0)
        credits_to_charge = min(max(int(settled_credits or 0), 0), reserved_credits)
        user.reserved_credits = max(int(user.reserved_credits or 0) - reserved_credits, 0)
        if credits_to_charge > 0:
            user.credits = int(user.credits or 0) - credits_to_charge
            user.total_credits_spent = int(user.total_credits_spent or 0) + credits_to_charge

        tx_metadata = dict(reservation.metadata_json or {})
        tx_metadata.update(metadata or {})
        tx_metadata.update(
            {
                "reservation_id": str(reservation.id),
                "reserved_credits": reserved_credits,
                "settled_credits": credits_to_charge,
            }
        )
        tx = self.repository.create_credit_transaction(
            {
                "user_id": reservation.user_id,
                "transaction_type": transaction_type,
                "amount": -credits_to_charge,
                "balance_after": user.credits,
                "description": description,
                "mission_policy_id": mission_policy_id,
                "mission_id": mission_id or reservation.mission_id,
                "operation_key": operation_key,
                "workspace_id": reservation.workspace_id,
                "task_id": None,
                "idempotency_key": f"reservation-settlement:{reservation.id}",
                "tx_metadata": tx_metadata,
            }
        )
        reservation.status = CreditReservationStatus.SETTLED
        reservation.settled_credits = credits_to_charge
        reservation.transaction_id = str(tx.id)
        reservation.metadata_json = {
            **dict(reservation.metadata_json or {}),
            "settlement_metadata": dict(metadata or {}),
        }
        await self._finish(reservation, tx)
        return reservation, tx

    async def release_reservation(
        self,
        reservation_id: str,
        *,
        reason: str | None = None,
    ) -> Any:
        """Release a reserved hold without creating a final ledger transaction."""
        reservation = await self.repository.get_reservation_for_update(reservation_id)
        if reservation is None:
            raise ValueError("Credit reservation not found")
        return await self._release_locked_reservation(
            reservation,
            status=CreditReservationStatus.RELEASED,
            reason=reason,
        )

    async def reactivate_reservation(
        self,
        reservation_id: str,
        *,
        reserved_credits: int,
        expires_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        reservation = await self.repository.get_reservation_for_update(
            reservation_id
        )
        if reservation is None:
            raise ValueError("Credit reservation not found")
        if reservation.status == CreditReservationStatus.RESERVED:
            return reservation
        if reservation.status == CreditReservationStatus.SETTLED:
            raise ValueError("Settled credit reservation cannot be reactivated")
        user = await self.repository.get_user_for_update(reservation.user_id)
        if user is None:
            raise ValueError("User not found")
        normalized_reserved = max(int(reserved_credits or 0), 0)
        spendable_credits = int(user.credits or 0) - int(user.reserved_credits or 0)
        if normalized_reserved > spendable_credits:
            raise CreditOverdraftLimitError(
                "insufficient spendable credits for reservation"
            )
        user.reserved_credits = int(user.reserved_credits or 0) + normalized_reserved
        reservation.status = CreditReservationStatus.RESERVED
        reservation.reserved_credits = normalized_reserved
        reservation.settled_credits = 0
        reservation.transaction_id = None
        reservation.expires_at = expires_at
        reservation.metadata_json = {
            **dict(reservation.metadata_json or {}),
            **dict(metadata or {}),
            "reactivated_at": datetime.now(UTC).isoformat(),
        }
        await self._finish(reservation)
        return reservation

    async def expire_reservation(
        self,
        reservation_id: str,
        *,
        now: datetime,
    ) -> Any:
        reservation = await self.repository.get_reservation_for_update(
            reservation_id
        )
        if reservation is None:
            raise ValueError("Credit reservation not found")
        expires_at = reservation.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        effective_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        if (
            reservation.status != CreditReservationStatus.RESERVED
            or expires_at is None
            or expires_at > effective_now
        ):
            return reservation
        return await self._release_locked_reservation(
            reservation,
            status=CreditReservationStatus.EXPIRED,
            reason="reservation expired",
        )

    async def _release_locked_reservation(
        self,
        reservation: Any,
        *,
        status: CreditReservationStatus,
        reason: str | None,
    ) -> Any:
        if reservation.status != CreditReservationStatus.RESERVED:
            return reservation
        user = await self.repository.get_user_for_update(reservation.user_id)
        if user is None:
            raise ValueError("User not found")
        user.reserved_credits = max(
            int(user.reserved_credits or 0)
            - max(int(reservation.reserved_credits or 0), 0),
            0,
        )
        reservation.status = status
        reservation.metadata_json = {
            **dict(reservation.metadata_json or {}),
            "release_reason": reason,
        }
        await self._finish(reservation)
        return reservation

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
        projected_credits = int(user.credits or 0) + signed_amount
        active_hold = int(user.reserved_credits or 0)
        if signed_amount < 0 and active_hold > 0 and projected_credits < active_hold:
            raise CreditOverdraftLimitError(
                "admin deduction cannot consume credits held by active work"
            )
        if signed_amount > 0:
            user.credits = projected_credits
            user.total_credits_earned += signed_amount
        else:
            user.credits = projected_credits
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
        rule = await self.repository.get_active_grant_rule(CreditGrantRuleType.REFERRAL_REFERRED)
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
        rule = await self.repository.get_active_grant_rule(CreditGrantRuleType.REFERRAL_REFERRER)
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

    async def _finish(self, *records: Any) -> None:
        refresh_records = [record for record in records if record is not None]
        if self.autocommit:
            await self.session.commit()
            for record in refresh_records:
                await self.session.refresh(record)
            return
        await self.session.flush()
        for record in refresh_records:
            await self.session.refresh(record)
