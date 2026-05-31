"""Canonical helpers for execution credit reservation metadata."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CREDIT_RESERVATION_ID_FIELD = "credit_reservation_id"
FEATURE_EXECUTION_RESERVATION_STATUS = "reserved"


def billing_metadata_from_params(params: Any) -> dict[str, Any]:
    """Read the canonical billing wrapper from execution params."""
    if not isinstance(params, Mapping):
        return {}
    billing = params.get("billing")
    if not isinstance(billing, Mapping):
        return {}
    return {str(key): value for key, value in billing.items() if isinstance(key, str)}


def reservation_id_from_params(params: Any) -> str | None:
    """Return the linked credit reservation id from canonical execution params."""
    value = str(billing_metadata_from_params(params).get(CREDIT_RESERVATION_ID_FIELD) or "").strip()
    return value or None


def feature_execution_reservation_key(execution_id: str) -> str:
    """Return the idempotency key for a feature execution reservation."""
    normalized_execution_id = str(execution_id or "").strip()
    if not normalized_execution_id:
        raise ValueError("feature execution reservation key requires execution_id")
    return f"feature_execution:{normalized_execution_id}"


def reservation_status(reservation: Any) -> str:
    """Return a normalized reservation lifecycle status from a payload/model."""
    return str(getattr(reservation, "status", "") or "").strip()


def reservation_is_active(reservation: Any) -> bool:
    """Return whether a reservation can be used to dispatch billable work."""
    return reservation_status(reservation) == FEATURE_EXECUTION_RESERVATION_STATUS


def merge_reservation_billing(params: dict[str, Any], reservation: Any) -> dict[str, Any]:
    """Return execution params with canonical billing metadata for reservation."""
    reservation_id = str(getattr(reservation, "id", "") or "").strip()
    if not reservation_id:
        raise ValueError("credit reservation payload requires id")
    existing_billing = billing_metadata_from_params(params)
    return {
        **dict(params),
        "billing": {
            **existing_billing,
            CREDIT_RESERVATION_ID_FIELD: reservation_id,
            "reserved_credits": int(getattr(reservation, "reserved_credits", 0) or 0),
            "reservation_status": reservation_status(reservation),
        },
    }
