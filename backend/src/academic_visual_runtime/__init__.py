"""Academic visual rendering runtime public surface."""

from .contracts import (
    AcademicFigureBrief,
    AcademicVisualCandidate,
    AcademicVisualExecutionContext,
    AcademicVisualReceipt,
    AcademicVisualRenderInput,
    CodeVisualPayload,
    ExactVisualLabel,
    FigureArtifactManifest,
    GenerativeVisualPayload,
    StructuredVisualPayload,
    VisualCandidateRef,
)
from .image_provider import ConfiguredGptImage2Provider
from .router import InvalidFigureStrategyError, route_visual
from .runtime import AcademicVisualRuntime, AcademicVisualRuntimeError, PreviewWriter

__all__ = [
    "AcademicFigureBrief",
    "AcademicVisualCandidate",
    "AcademicVisualExecutionContext",
    "AcademicVisualReceipt",
    "AcademicVisualRenderInput",
    "AcademicVisualRuntime",
    "AcademicVisualRuntimeError",
    "CodeVisualPayload",
    "ConfiguredGptImage2Provider",
    "ExactVisualLabel",
    "FigureArtifactManifest",
    "GenerativeVisualPayload",
    "InvalidFigureStrategyError",
    "PreviewWriter",
    "StructuredVisualPayload",
    "VisualCandidateRef",
    "route_visual",
]
