"""Bound stdout/stderr streams for sandbox Python jobs."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from src.agents.harness.output_budget import BudgetedText, budget_text_output


async def budget_script_streams(
    *,
    sandbox: Any,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    stdout: str,
    stderr: str,
) -> tuple[BudgetedText, BudgetedText]:
    output_budget = _output_budget(sandbox_policy)
    context = SimpleNamespace(
        workspace_id=workspace_id,
        execution_id=execution_id,
        node_id=node_id,
        invocation_id=node_id,
    )
    stdout_budget = await budget_text_output(
        text=stdout,
        tool_name="sandbox.run_python.stdout",
        context=context,
        sandbox=sandbox,
        output_budget=output_budget,
        fallback_max_chars=_stream_max_chars(output_budget, "stdout"),
    )
    stderr_budget = await budget_text_output(
        text=stderr,
        tool_name="sandbox.run_python.stderr",
        context=context,
        sandbox=sandbox,
        output_budget=output_budget,
        fallback_max_chars=_stream_max_chars(output_budget, "stderr"),
    )
    return stdout_budget, stderr_budget


def _output_budget(sandbox_policy: Mapping[str, Any]) -> dict[str, Any]:
    value = sandbox_policy.get("output_budget")
    return dict(value) if isinstance(value, Mapping) else {}


def _stream_max_chars(output_budget: Mapping[str, Any], stream: str) -> int:
    return int(
        output_budget.get(f"{stream}_max_chars")
        or output_budget.get("stream_max_chars")
        or 12_000
    )
