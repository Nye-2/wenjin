"""Tests for canonical credit reservation metadata helpers."""
from __future__ import annotations

from types import SimpleNamespace

from src.billing.reservation_metadata import (
    FEATURE_EXECUTION_RESERVATION_STATUS,
    billing_metadata_from_params,
    feature_execution_reservation_key,
    merge_reservation_billing,
    reservation_id_from_params,
    reservation_is_active,
)


def test_reservation_id_from_params_reads_canonical_billing_wrapper() -> None:
    params = {
        "brief": {"capability_id": "idea_to_thesis_manuscript"},
        "billing": {"credit_reservation_id": " reservation-1 "},
    }

    assert reservation_id_from_params(params) == "reservation-1"


def test_merge_reservation_billing_preserves_brief_and_existing_billing_metadata() -> None:
    params = {
        "brief": {"capability_id": "idea_to_thesis_manuscript"},
        "billing": {"source": "previous", "reserved_credits": 12},
    }
    reservation = SimpleNamespace(id="reservation-2", reserved_credits=34, status="reserved")

    merged = merge_reservation_billing(params, reservation)

    assert merged == {
        "brief": {"capability_id": "idea_to_thesis_manuscript"},
        "billing": {
            "source": "previous",
            "credit_reservation_id": "reservation-2",
            "reserved_credits": 34,
            "reservation_status": "reserved",
        },
    }
    assert params["billing"]["reserved_credits"] == 12


def test_reservation_helpers_normalize_status_and_feature_key() -> None:
    active = SimpleNamespace(id="reservation-1", status=FEATURE_EXECUTION_RESERVATION_STATUS)
    released = SimpleNamespace(id="reservation-2", status="released")

    assert reservation_is_active(active) is True
    assert reservation_is_active(released) is False
    assert feature_execution_reservation_key(" exec-1 ") == "feature_execution:exec-1"
    assert billing_metadata_from_params({"billing": {"reserved_credits": 3}}) == {"reserved_credits": 3}
