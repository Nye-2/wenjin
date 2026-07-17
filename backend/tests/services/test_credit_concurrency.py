"""Structural tests for DataService-owned credit concurrency.

Runtime CreditService no longer owns row locks or direct SQL. It performs
admission checks through DataService read projections and writes through
DataService atomic ledger commands.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from src.dataservice.domains.credit.service import DataServiceCreditService
from src.services.credit_service import CreditService


def _call_attrs(source: str) -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    return [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]


def test_capacity_preview_uses_dataservice_summary_projection() -> None:
    source = inspect.getsource(CreditService.preview_thread_turn_capacity)
    calls = _call_attrs(source)

    assert "get_credit_summary" in calls
    assert "_get_user_for_update" not in calls
    assert "with_for_update" not in source


def test_credit_service_has_no_runtime_db_lock_helper() -> None:
    assert not hasattr(CreditService, "_get_user_for_update")


def test_dataservice_reservation_creation_uses_user_row_lock() -> None:
    source = inspect.getsource(DataServiceCreditService.create_reservation)
    calls = _call_attrs(source)

    assert "get_user_for_update" in calls
    assert "reserved_credits" in source
