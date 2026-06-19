"""Tests for thesis execution package exports."""

from __future__ import annotations

import src.thesis.execution as execution


def test_execution_package_does_not_export_old_figure_product_api() -> None:
    """Old thesis-only figure helpers are not part of the product API."""
    old_figure_exports = {"generate_figure", "GenerateFigureResult", "FigureStrategy"}

    for name in old_figure_exports:
        assert not hasattr(execution, name)
        assert name not in execution.__all__


def test_execution_package_keeps_latex_and_service_injection_exports() -> None:
    """LaTeX tool and execution service injection remain public."""
    expected_exports = {
        "compile_latex",
        "CompileLatexResult",
        "get_execution_service",
        "set_execution_service",
        "ExecutionServiceProtocol",
    }

    assert expected_exports.issubset(set(execution.__all__))
    assert callable(execution.compile_latex)
    assert execution.CompileLatexResult is not None
    assert callable(execution.get_execution_service)
    assert callable(execution.set_execution_service)
    assert execution.ExecutionServiceProtocol is not None
