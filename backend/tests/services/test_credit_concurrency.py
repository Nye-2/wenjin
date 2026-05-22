"""Structural tests for DataService-owned credit concurrency.

Runtime CreditService no longer owns row locks or direct SQL. It performs
admission checks through DataService read projections and writes through
DataService atomic ledger commands.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from src.services.credit_service import CreditService


def _call_attrs(source: str) -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    return [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]


def test_can_start_thread_turn_uses_dataservice_balance_projection() -> None:
    source = inspect.getsource(CreditService.can_start_thread_turn)
    calls = _call_attrs(source)

    assert "get_balance" in calls
    assert "_get_user_for_update" not in calls
    assert "with_for_update" not in source


def test_can_start_feature_task_uses_dataservice_balance_projection() -> None:
    source = inspect.getsource(CreditService.can_start_feature_task)
    calls = _call_attrs(source)

    assert "get_balance" in calls
    assert "_get_user_for_update" not in calls
    assert "with_for_update" not in source


def test_credit_service_has_no_runtime_db_lock_helper() -> None:
    assert not hasattr(CreditService, "_get_user_for_update")
