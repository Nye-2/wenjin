"""Deterministic strategy validation for academic visual requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.academic_visual_runtime.contracts import AcademicVisualRenderInput
from src.contracts.figure_generation import (
    CHART_CODE_STRATEGIES,
    GENERATIVE_FIGURE_TYPES,
    STRUCTURED_STRATEGIES,
)

RouteFamily = Literal["code", "structured", "generative", "hybrid"]


@dataclass(frozen=True, slots=True)
class VisualRoute:
    family: RouteFamily
    renderer_id: str


class InvalidFigureStrategyError(ValueError):
    """The proposed payload cannot execute the pinned FigureSpec strategy."""


def route_visual(request: AcademicVisualRenderInput) -> VisualRoute:
    strategy = request.brief.figure_spec.strategy
    payload_kind = request.render.kind

    if strategy in CHART_CODE_STRATEGIES or strategy == "python_schematic":
        _require(payload_kind == "code", strategy, "code")
        return VisualRoute(family="code", renderer_id=strategy)
    if strategy in STRUCTURED_STRATEGIES:
        _require(payload_kind == "structured", strategy, "structured")
        return VisualRoute(family="structured", renderer_id=strategy)
    if strategy == "llm_image":
        _require(payload_kind == "generative", strategy, "generative")
        _require(request.brief.figure_spec.figure_type in GENERATIVE_FIGURE_TYPES, strategy, "a supported explanatory figure type")
        _require(not request.brief.exact_labels, strategy, "no exact labels")
        return VisualRoute(family="generative", renderer_id="gpt-image-2")
    if strategy == "hybrid":
        _require(payload_kind == "generative", strategy, "generative")
        _require(request.brief.figure_spec.figure_type in GENERATIVE_FIGURE_TYPES, strategy, "a supported explanatory figure type")
        _require(bool(request.brief.exact_labels), strategy, "exact labels")
        return VisualRoute(family="hybrid", renderer_id="gpt-image-2+deterministic-overlay")
    raise InvalidFigureStrategyError(f"unsupported academic visual strategy: {strategy}")


def _require(condition: bool, strategy: str, expected: str) -> None:
    if not condition:
        raise InvalidFigureStrategyError(f"strategy '{strategy}' requires {expected}")


__all__ = ["InvalidFigureStrategyError", "VisualRoute", "route_visual"]
